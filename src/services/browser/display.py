"""Stop the Xvfb of a runner that could not stop it itself.

In virtual mode the runner starts Xvfb and stops it when it exits. A runner
that is killed or crashes never gets there, and killing the runner does not
reach Xvfb: Camoufox starts it in its own session. So the runner records which
Xvfb it started, and whoever sees the runner gone stops it.

A record is keyed by the runner's PID and pins both processes by their start
time, so a relaunch of the same profile, or a PID the kernel has handed to
another process (another profile's Xvfb included), is never touched. Records
live in a private per-user directory under the system temp dir; one left from
before a reboot is inert, as its start times no longer match anything.

Virtual mode is Linux-only, and so is this (it reads /proc); elsewhere every
function is a no-op.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import signal
import stat
import tempfile
import time
from typing import Any

from ...core.logging import get_logger

logger = get_logger("browser.display")

_PROC = pathlib.Path("/proc")
_warned_dir = False


def _run_dir() -> pathlib.Path | None:
    """The private record directory, or None where records are not supported."""
    if os.name != "posix" or not _PROC.is_dir():
        return None
    path = pathlib.Path(tempfile.gettempdir()) / f"foxprofile-{os.getuid()}"
    try:
        path.mkdir(mode=0o700, exist_ok=True)
        st = path.lstat()
    except OSError:
        return None
    # The temp dir is shared: only trust a directory that is really ours.
    if (
        not stat.S_ISDIR(st.st_mode)
        or st.st_uid != os.getuid()
        or st.st_mode & (stat.S_IRWXG | stat.S_IRWXO)
    ):
        global _warned_dir
        if not _warned_dir:
            _warned_dir = True
            logger.warning(
                "Not using %s for Xvfb records (not a private directory owned by this "
                "user); a killed profile's Xvfb will not be stopped",
                path,
            )
        return None
    return path


def _proc_stat(pid: int) -> tuple[str, int] | None:
    """(state, start time in clock ticks after boot) of a process, if it exists."""
    try:
        data = (_PROC / str(pid) / "stat").read_text()
        # comm (field 2) is in parentheses and may contain spaces or ")".
        fields = data[data.rindex(")") + 2 :].split()
        return fields[0], int(fields[19])
    except (OSError, ValueError, IndexError):
        return None


def _running(pid: int, start: int) -> bool:
    """Whether the process recorded as (pid, start) still runs (a zombie does not)."""
    info = _proc_stat(pid)
    return info is not None and info[1] == start and info[0] != "Z"


def _is_recorded_xvfb(pid: int, start: int) -> bool:
    if not _running(pid, start):
        return False
    try:
        return (_PROC / str(pid) / "comm").read_text().strip() == "Xvfb"
    except OSError:
        return False


def record(xvfb_pid: int, display: str) -> None:
    """Record the Xvfb this runner started, before anything can kill the runner."""
    run_dir = _run_dir()
    runner = _proc_stat(os.getpid())
    xvfb = _proc_stat(xvfb_pid)
    if run_dir is None or runner is None or xvfb is None:
        return
    data = {
        "runner": [os.getpid(), runner[1]],
        "xvfb": [xvfb_pid, xvfb[1]],
        "display": int(display.lstrip(":")),
    }
    tmp = run_dir / f".{os.getpid()}.tmp"
    try:
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, run_dir / f"{os.getpid()}.json")
    except OSError as e:
        logger.warning("Could not record Xvfb %s: %s", xvfb_pid, e)


def clear() -> None:
    """Drop this runner's record once it has stopped its Xvfb itself."""
    run_dir = _run_dir()
    if run_dir is not None:
        with contextlib.suppress(OSError):
            (run_dir / f"{os.getpid()}.json").unlink()


def _load(path: pathlib.Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        runner_pid, runner_start = (int(v) for v in data["runner"])
        xvfb_pid, xvfb_start = (int(v) for v in data["xvfb"])
        return {
            "runner": (runner_pid, runner_start),
            "xvfb": (xvfb_pid, xvfb_start),
            "display": int(data["display"]),
        }
    except (OSError, ValueError, TypeError, KeyError):
        return None


def _stop(rec: dict[str, Any], grace: float) -> bool:
    pid, start = rec["xvfb"]
    if not _is_recorded_xvfb(pid, start):
        return False
    with contextlib.suppress(ProcessLookupError, PermissionError):
        # SIGTERM first: Xvfb then removes its own lock file and socket.
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + grace
        while _running(pid, start) and time.monotonic() < deadline:
            time.sleep(0.05)
        if _running(pid, start):
            os.kill(pid, signal.SIGKILL)
            deadline = time.monotonic() + 1
            while _running(pid, start) and time.monotonic() < deadline:
                time.sleep(0.05)
            if not _running(pid, start):
                _remove_display_files(rec["display"], pid)
    return True


def _remove_display_files(display: int, pid: int) -> None:
    """Remove the lock and socket a killed Xvfb left, if they are still its own.

    Stranded ones push every later display number up. But once the Xvfb is
    dead a new one may already have taken the number, so only touch them while
    the lock still names the killed PID.
    """
    lock = pathlib.Path(f"/tmp/.X{display}-lock")
    try:
        if int(lock.read_text().strip()) != pid:
            return
    except (OSError, ValueError):
        return
    for leftover in (lock, pathlib.Path(f"/tmp/.X11-unix/X{display}")):
        with contextlib.suppress(OSError):
            leftover.unlink()


def stop_for_runner(runner_pid: int, grace: float = 2.0) -> bool:
    """Stop the Xvfb recorded by a runner that has exited. True if one was stopped."""
    run_dir = _run_dir()
    if run_dir is None:
        return False
    path = run_dir / f"{runner_pid}.json"
    rec = _load(path)
    if rec is None or _running(*rec["runner"]):
        # No record (the runner cleaned up), or the PID is already a new runner.
        return False
    stopped = _stop(rec, grace)
    with contextlib.suppress(OSError):
        path.unlink()
    return stopped


def sweep_stale(grace: float = 2.0) -> int:
    """Stop the Xvfbs of runners that are gone (e.g. killed with the whole app)."""
    run_dir = _run_dir()
    if run_dir is None:
        return 0
    stopped = 0
    for path in run_dir.glob("*.json"):
        rec = _load(path)
        if rec is not None and _running(*rec["runner"]):
            continue
        if rec is not None and _stop(rec, grace):
            stopped += 1
        with contextlib.suppress(OSError):
            path.unlink()
    # Temp files of runners killed between writing and renaming their record.
    for tmp in run_dir.glob(".*.tmp"):
        with contextlib.suppress(ValueError, OSError):
            if not (_PROC / str(int(tmp.name[1:-4]))).exists():
                tmp.unlink()
    return stopped
