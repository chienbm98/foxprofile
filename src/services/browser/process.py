import contextlib
import os
import pathlib
import signal
import subprocess
import sys
from collections.abc import Callable

from ...core.config import DATA_DIR
from ...core.logging import get_logger
from ...models.profile import Profile
from . import display

logger = get_logger("browser.process")


_PROJECT_ROOT = str(pathlib.Path(__file__).parents[3])


def spawn_browser(profile: Profile) -> subprocess.Popen:
    """Spawn a Camoufox browser subprocess for the given profile."""
    script = os.path.join(pathlib.Path(__file__).parent, "runner.py")
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = _PROJECT_ROOT + (
        os.pathsep + existing_pythonpath if existing_pythonpath else ""
    )
    return subprocess.Popen(
        [
            sys.executable,
            script,
            profile.name,
            str(profile.proxy),
            profile.os_type,
            profile.timezone or "",
            profile.locale or "",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=pathlib.Path.cwd(),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        # Own process group on POSIX, so stopping a profile can take down what
        # the runner started (Xvfb, the Playwright driver, Firefox) even when
        # the runner itself has to be killed.
        start_new_session=os.name == "posix",
    )


def terminate(proc: subprocess.Popen, name: str, timeout: int = 5) -> None:
    """Gracefully terminate a browser process, force-kill on timeout."""
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
            logger.info("Browser %s terminated gracefully", name)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=1)
            logger.warning("Browser %s force killed after timeout", name)
    except Exception as e:
        logger.exception("Error terminating browser %s: %s", name, e)
    finally:
        cleanup(proc, name)


def cleanup(proc: subprocess.Popen, name: str) -> None:
    """Stop what an exited runner left behind: its process group and its Xvfb.

    Xvfb runs in its own session, so the process group does not cover it; the
    runner records its PID in the profile directory instead.
    """
    if os.name != "posix" or proc.poll() is None:
        return
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, signal.SIGKILL)
    display.stop_recorded(os.path.join(os.getcwd(), DATA_DIR, name))


def wait_for_exit(
    proc: subprocess.Popen,
    name: str,
    notify_stopped: Callable[[], None],
) -> None:
    """Block until the process exits, then fire the callback."""
    try:
        proc.wait()
    except Exception as e:
        logger.exception("Wait error for profile %s: %s", name, e)
    finally:
        # A runner that died on its own (crash, OOM kill) never ran its cleanup.
        cleanup(proc, name)
        notify_stopped()
