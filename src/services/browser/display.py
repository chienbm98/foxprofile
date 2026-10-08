"""Track the Xvfb a profile's runner started, so it can be stopped from outside.

Camoufox starts Xvfb in its own session (start_new_session), so killing the
runner's process group does not reach it. The runner records the PID next to
the profile's data; whoever sees the runner exit stops that Xvfb if it is
still running.
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import signal
import time

PID_FILE = "xvfb.pid"


def pid_path(profile_dir: str) -> pathlib.Path:
    return pathlib.Path(profile_dir) / PID_FILE


def record(profile_dir: str, pid: int) -> None:
    path = pid_path(profile_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(pid), encoding="utf-8")


def clear(profile_dir: str) -> None:
    with contextlib.suppress(OSError):
        pid_path(profile_dir).unlink()


def _is_xvfb(pid: int) -> bool:
    # The PID may have been reused since it was recorded; only ever stop an Xvfb.
    try:
        return pathlib.Path(f"/proc/{pid}/comm").read_text().strip() == "Xvfb"
    except OSError:
        return False


def stop_recorded(profile_dir: str, grace: float = 2.0) -> bool:
    """Stop the Xvfb recorded for this profile, if it is still running."""
    path = pid_path(profile_dir)
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    stopped = False
    if os.name == "posix" and _is_xvfb(pid):
        # SIGTERM first: Xvfb then removes its own /tmp/.X<n>-lock and socket.
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(pid, signal.SIGTERM)
            deadline = time.monotonic() + grace
            while _is_xvfb(pid) and time.monotonic() < deadline:
                time.sleep(0.05)
            if _is_xvfb(pid):
                os.kill(pid, signal.SIGKILL)
            stopped = True
    clear(profile_dir)
    return stopped
