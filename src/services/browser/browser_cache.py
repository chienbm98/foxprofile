"""Keep Camoufox's browser cache from being thrown away by accident.

Camoufox keeps the browser (about 2.4 GB) in one per-user folder. When that folder holds a
browser but lacks its `.0.5_FLAG` marker, Camoufox decides it is old and deletes the whole
folder, then downloads 1.3 GB again at the next launch. Other tools that share the folder (a
different Camoufox library version, a Node wrapper) can remove the marker, which is how a
profile that opened in seconds yesterday suddenly "hangs" for minutes today.
"""

from __future__ import annotations

import pathlib
from typing import Any

from ...core.logging import get_logger

logger = get_logger("browser.cache")

FLAG = ".0.5_FLAG"
_EXE_NAMES = ("camoufox.exe", "camoufox", "camoufox-bin")


def cache_dir() -> pathlib.Path:
    from camoufox import pkgman

    return pathlib.Path(pkgman.INSTALL_DIR)


def _has_browser(root: pathlib.Path) -> str | None:
    """The version folder of an installed browser under root/browsers, if any."""
    browsers = root / "browsers"
    if not browsers.is_dir():
        return None
    for exe in _EXE_NAMES:
        for found in browsers.glob(f"*/*/{exe}"):
            return found.parent.name
    return None


def status() -> dict[str, Any]:
    root = cache_dir()
    version = _has_browser(root)
    return {
        "dir": str(root),
        "installed": version is not None,
        "version": version,
        "marker": (root / FLAG).exists(),
    }


def repair_marker() -> bool:
    """Put the marker back when a browser is installed but the marker is gone, so Camoufox
    keeps it instead of deleting and re-downloading it. True when something was repaired."""
    try:
        root = cache_dir()
        if _has_browser(root) and not (root / FLAG).exists():
            (root / FLAG).touch()
            logger.warning("Restored %s in %s: the browser cache was about to be wiped", FLAG, root)
            return True
    except Exception as e:  # never stop a launch over a repair that did not work
        logger.debug("Could not check the browser cache: %s", e)
    return False
