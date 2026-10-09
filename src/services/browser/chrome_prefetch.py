"""Download the Chrome engine in the background once a Chrome profile exists.

The Chrome runner installs the browser itself on first launch, but the build is
~140-190 MB; starting the download when the profile is created means the first
launch usually finds it ready. Only one prefetch runs per process.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from ...core.logging import get_logger
from ...core.strings import get_string

logger = get_logger("browser.chrome_prefetch")

_lock = threading.Lock()
_thread: threading.Thread | None = None


def is_installed() -> bool:
    from chrome_engine import fetch

    return fetch.installed_executable() is not None


def start(log: Callable[[str], None] | None = None) -> bool:
    """Start downloading the engine unless it is installed or already downloading.

    Returns True if a download was started.
    """
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            return False
        try:
            if is_installed():
                return False
        except Exception as e:  # unsupported host, unreadable cache dir...
            logger.warning("Cannot check the Chrome engine install: %s", e)
            return False
        _thread = threading.Thread(target=_run, args=(log,), daemon=True, name="chrome-prefetch")
        _thread.start()
        return True


def _run(log: Callable[[str], None] | None) -> None:
    from chrome_engine import fetch

    def say(message: str) -> None:
        logger.info(message)
        if log:
            log(message)

    say(get_string("chrome_engine_downloading"))
    try:
        fetch.install()
    except Exception as e:
        logger.exception("Chrome engine download failed")
        say(get_string("chrome_engine_download_failed", error=e))
        return
    say(get_string("chrome_engine_ready"))
