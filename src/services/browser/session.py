"""Open tabs that survive a profile restart.

Camoufox disables Firefox's own session restore, and FoxProfile stops a
browser by terminating its process, so Firefox never gets to save its session
anyway. The runner instead snapshots the open tabs' URLs to tabs.json in the
profile directory whenever they change, and reopens them on the next launch.
"""

from __future__ import annotations

import json
import os
import pathlib
from urllib.parse import urlparse

from ...core.logging import get_logger

logger = get_logger("browser.session")

TABS_FILE = "tabs.json"
MAX_TABS = 30
_RESTORABLE_SCHEMES = ("http", "https")


def tabs_path(profile_dir: str) -> pathlib.Path:
    return pathlib.Path(profile_dir) / TABS_FILE


def restorable(urls: list[str]) -> list[str]:
    """Keep the URLs worth reopening: http(s) only, at most MAX_TABS."""
    kept = [u for u in urls if isinstance(u, str) and urlparse(u).scheme in _RESTORABLE_SCHEMES]
    return kept[:MAX_TABS]


def save(profile_dir: str, urls: list[str]) -> bool:
    """Write the tab list atomically. Returns False (and keeps the old file) when
    there is nothing restorable, so closing the last tab never wipes the session."""
    urls = restorable(urls)
    if not urls:
        return False
    path = tabs_path(profile_dir)
    tmp = path.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps({"tabs": urls}, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        logger.warning("Could not save open tabs for %s: %s", profile_dir, e)
        return False
    return True


def load(profile_dir: str) -> list[str]:
    path = tabs_path(profile_dir)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.warning("Ignoring unreadable %s: %s", path, e)
        return []
    tabs = data.get("tabs") if isinstance(data, dict) else None
    return restorable(tabs) if isinstance(tabs, list) else []
