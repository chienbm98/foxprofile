"""Per-profile fingerprint persistence.

Camoufox draws a fresh device on every launch unless one is passed in. A
profile that keeps its cookies but changes screen, GPU and fonts on each launch
looks like a spoofed browser, so the first launch draws one real-device record
from the local library (devices.py), resolves it through Camoufox once, and
saves the result as fingerprint.json (v2). Every later launch starts from that
frozen "masked device"; fpsettings.py applies the profile's per-item modes on top.
"""

import json
import os
import pathlib
import uuid
from typing import Any

from ...core.config import FINGERPRINT_FILE
from ...core.logging import get_logger
from . import devices

logger = get_logger("browser.fingerprint")

VERSION = 2
# Config keys that belong to one launch (geo, WebRTC, add-ons, switches), not to the device.
_PER_LAUNCH_PREFIXES = ("locale:", "geolocation:", "webrtc:", "humanize", "certificate")
_PER_LAUNCH_KEYS = ("timezone", "addons", "debug", "allowMainWorld", "allowAddonNewtab")


def fingerprint_path(profile_dir: str) -> str:
    return os.path.join(profile_dir, FINGERPRINT_FILE)


def decode_config(env: dict) -> dict[str, Any]:
    """The Camoufox config carried by the CAMOU_CONFIG_<n> chunks of a launch env."""
    chunks = sorted(
        (int(k.rsplit("_", 1)[1]), v) for k, v in env.items() if k.startswith("CAMOU_CONFIG_")
    )
    return json.loads("".join(v for _, v in chunks))


def _device_keys(config: dict) -> dict[str, Any]:
    return {
        k: v
        for k, v in config.items()
        if k not in _PER_LAUNCH_KEYS and not k.startswith(_PER_LAUNCH_PREFIXES)
    }


def _freeze(os_type: str) -> tuple[str, dict[str, Any]]:
    """Draw a library record and resolve it into a Camoufox device config."""
    from camoufox.fingerprints import clamp_window_dimensions, clamp_window_position
    from camoufox.utils import launch_options

    record = devices.pick(os_type)
    common = {"os": os_type, "headless": True, "i_know_what_im_doing": True}
    first = _device_keys(decode_config(launch_options(fingerprint_preset=record, **common)["env"]))
    # A preset has no window geometry; the second pass makes Camoufox draw it, and it
    # is kept too, or every launch would open with a different window.
    device = _device_keys(decode_config(launch_options(config=dict(first), **common)["env"]))
    # Camoufox draws these only some of the time; unset they would be redrawn each launch.
    for key in ("screen.availLeft", "screen.availTop", "window.screenX"):
        device.setdefault(key, 0)
    device.setdefault("window.screenY", device["screen.availTop"])
    # Camoufox swaps in this machine's core count when it cannot pin cores (macOS);
    # keep the record's, or every profile on one host shows the same count.
    if cores := record["navigator"].get("hardwareConcurrency"):
        device["navigator.hardwareConcurrency"] = cores
    # The window was drawn apart from the preset's screen; keep it inside it.
    clamp_window_dimensions(device)
    clamp_window_position(device)
    return record["id"], device


def load_saved(profile_dir: str) -> dict[str, Any] | None:
    """The saved device config (v2 file), or None. Never draws a device."""
    try:
        data = json.loads(pathlib.Path(fingerprint_path(profile_dir)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if data.get("version") == VERSION and isinstance(data.get("device"), dict):
        return data["device"]
    return None


def load_or_create(profile_dir: str, os_type: str) -> dict[str, Any]:
    """Return the profile's frozen device config, drawing it on first use.

    A v1 file (fpgen fingerprint) or one for another OS is replaced.
    """
    path = pathlib.Path(fingerprint_path(profile_dir))
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if (
                data.get("version") == VERSION
                and data.get("os") == os_type
                and isinstance(data.get("device"), dict)
            ):
                # Briefly frozen: JS-only DPR that media queries contradict.
                data["device"].pop("window.devicePixelRatio", None)
                return data["device"]
            logger.info("Fingerprint outdated or for another OS in %s, regenerating", profile_dir)
        except (OSError, ValueError) as e:
            logger.warning("Unreadable fingerprint in %s (%s), regenerating", path, e)

    source, device = _freeze(os_type)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": VERSION, "os": os_type, "source": source, "device": device}),
        encoding="utf-8",
    )
    logger.info("Froze device %s for %s (%s)", source, profile_dir, os_type)
    return device


def noise_key(profile_dir: str) -> str:
    """The profile's canvas/WebGL noise key ("{uuid}"), kept in fingerprint.json next to
    the device so a new fingerprint also gets new noise. Call after load_or_create.

    A patched Camoufox reads it as the browsing session key, so noise stays the same
    across launches while still differing per site; stock Camoufox ignores the pref.
    """
    path = pathlib.Path(fingerprint_path(profile_dir))
    data = json.loads(path.read_text(encoding="utf-8"))
    key = data.get("noise_key")
    if not (isinstance(key, str) and len(key) == 38):
        key = data["noise_key"] = "{" + str(uuid.uuid4()) + "}"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(path)
    return key


# The Chrome engine's equivalent of fingerprint.json (chrome_engine/persona.py).
CHROME_PERSONA_FILE = "chrome_persona.json"
_NAVIGATOR_PLATFORM = {"windows": "Win32", "macos": "MacIntel", "linux": "Linux x86_64"}


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
    device = data.get("device")
    if data.get("version") != VERSION or not isinstance(device, dict):
        return None
    width = device.get("screen.width")
    return {
        "os": data.get("os"),
        "platform": device.get("navigator.platform"),
        "screen": f"{width}x{device.get('screen.height')}" if width else None,
        "hardware_concurrency": device.get("navigator.hardwareConcurrency"),
        "webgl_renderer": device.get("webGl:renderer"),
        "source": data.get("source"),
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
        # The Chrome engine sets the screen only when headless; headed it is the
        # real monitor, so there is no stored value to report.
        "screen": None,
        "hardware_concurrency": data.get("hardware_concurrency"),
    }
