import contextlib
import os
import pathlib
import subprocess
import sys
from collections.abc import Callable

from ...core.logging import get_logger
from ...models.profile import Profile
from . import display

logger = get_logger("browser.process")


_PROJECT_ROOT = str(pathlib.Path(__file__).parents[3])


def runner_command(profile: Profile) -> list[str]:
    """The runner for the profile's engine; both speak the same stdout protocol."""
    if profile.engine == "chrome":
        runner = ["-m", "chrome_engine.runner"]
    else:
        runner = [os.path.join(pathlib.Path(__file__).parent, "runner.py")]
    return [
        sys.executable,
        *runner,
        profile.name,
        str(profile.proxy),
        profile.os_type,
        profile.timezone or "",
        profile.locale or "",
    ]


def spawn_browser(profile: Profile) -> subprocess.Popen:
    """Spawn the browser subprocess for the given profile."""
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = _PROJECT_ROOT + (
        os.pathsep + existing_pythonpath if existing_pythonpath else ""
    )
    return subprocess.Popen(
        runner_command(profile),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=pathlib.Path.cwd(),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )


def _descendants(proc: subprocess.Popen) -> list:
    """The runner's children (the driver, the browser, its tabs), found before it is stopped:
    once the runner is gone they can no longer be traced back to it."""
    try:
        import psutil

        return psutil.Process(proc.pid).children(recursive=True)
    except Exception:  # psutil missing, or the process is already gone
        return []


def _reap(children: list, name: str, grace: float) -> None:
    """Give the browser `grace` seconds to close by itself, then kill what is left. A stick or
    disk that writes slowly needs the time; a browser left behind keeps its profile locked."""
    if not children:
        return
    try:
        import psutil

        _, alive = psutil.wait_procs(children, timeout=grace)
        for child in alive:
            with contextlib.suppress(Exception):
                child.kill()
        if alive:
            logger.warning(
                "Browser %s: killed %d process(es) that would not close", name, len(alive)
            )
    except Exception as e:
        logger.debug("Reaping the browser of %s failed: %s", name, e)


def terminate(proc: subprocess.Popen, name: str, timeout: int = 5, grace: float = 20.0) -> None:
    """Gracefully terminate a browser process, force-kill on timeout, and make sure nothing
    the runner started is left running."""
    if proc.poll() is not None:
        return
    children = _descendants(proc)
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
        cleanup(proc)
        _reap(children, name, grace)


def cleanup(proc: subprocess.Popen) -> None:
    """Stop the Xvfb of a runner that exited without stopping it (killed, crashed)."""
    if proc.poll() is not None:
        display.stop_for_runner(proc.pid)


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
        cleanup(proc)
        notify_stopped()
