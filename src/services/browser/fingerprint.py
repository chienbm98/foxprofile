"""Per-profile fingerprint persistence.

Camoufox generates a fresh fingerprint on every launch unless one is passed
in. A profile that keeps its cookies but changes screen, GPU and fonts on each
launch looks like a spoofed browser, so the first launch generates a
fingerprint and every later launch reuses it from the profile's data dir.
"""

import json
import os
import pathlib
from typing import Any

from ...core.config import FINGERPRINT_FILE
from ...core.logging import get_logger

logger = get_logger("browser.fingerprint")


def fingerprint_path(profile_dir: str) -> str:
    return os.path.join(profile_dir, FINGERPRINT_FILE)


def load_or_create(profile_dir: str, os_type: str) -> dict[str, Any]:
    """Return the profile's saved fingerprint, generating it on first use."""
    path = pathlib.Path(fingerprint_path(profile_dir))
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("os") == os_type and isinstance(data.get("fingerprint"), dict):
                return data["fingerprint"]
            logger.info("Fingerprint OS changed for %s, regenerating", profile_dir)
        except (OSError, ValueError) as e:
            logger.warning("Unreadable fingerprint in %s (%s), regenerating", path, e)

    from camoufox.fingerprints import generate_fingerprint

    fingerprint = generate_fingerprint(os=os_type)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"os": os_type, "fingerprint": fingerprint}),
        encoding="utf-8",
    )
    logger.info("Generated fingerprint for %s (%s)", profile_dir, os_type)
    return fingerprint


# The Chrome engine's equivalent of fingerprint.json (chrome_engine/persona.py).
CHROME_PERSONA_FILE = "chrome_persona.json"
_NAVIGATOR_PLATFORM = {"windows": "Win32", "macos": "MacIntel", "linux": "Linux x86_64"}
# The Chrome engine always presents this screen (chrome_engine/engine.py).
_CHROME_SCREEN = "1920x1080"


def reset(profile_dir: str) -> bool:
    """Delete the saved fingerprint so the next launch generates a new one."""
    removed = False
    for name in (FINGERPRINT_FILE, CHROME_PERSONA_FILE):
        path = pathlib.Path(profile_dir) / name
        if path.exists():
            path.unlink()
            removed = True
    return removed


_summary_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}


def summary(profile_dir: str) -> dict[str, Any] | None:
    """Return the headline values of the saved fingerprint, if any.

    Cached by file mtime: the UI asks for every visible card on each refresh
    and the file is a few hundred KB.
    """
    path = pathlib.Path(fingerprint_path(profile_dir))
    reader = _read_summary
    if not path.exists():
        path = pathlib.Path(profile_dir) / CHROME_PERSONA_FILE
        reader = _read_chrome_summary
    try:
        mtime = path.stat().st_mtime
    except OSError:
        _summary_cache.pop(str(path), None)
        return None
    cached = _summary_cache.get(str(path))
    if cached and cached[0] == mtime:
        return cached[1]
    result = reader(path)
    _summary_cache[str(path)] = (mtime, result)
    return result


def _read_summary(path: pathlib.Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    fp = data.get("fingerprint", {})
    navigator = fp.get("navigator", {}) or {}
    screen = fp.get("screen", {}) or {}
    # The stored userAgent carries the generator's Firefox version; Camoufox
    # rewrites it to the installed version at launch, so it is not reported.
    return {
        "os": data.get("os"),
        "platform": navigator.get("platform"),
        "screen": f"{screen.get('width')}x{screen.get('height')}" if screen.get("width") else None,
        "hardware_concurrency": navigator.get("hardwareConcurrency"),
    }


def _read_chrome_summary(path: pathlib.Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    platform = data.get("platform")
    return {
        "os": platform,
        "platform": _NAVIGATOR_PLATFORM.get(platform),
        "screen": _CHROME_SCREEN,
        "hardware_concurrency": data.get("hardware_concurrency"),
    }
