"""Local library of real desktop Firefox devices (src/assets/devices/devices.json).

Records use Camoufox's fingerprint-preset shape plus "id" and "source", grouped
by os ("windows", "macos", "linux"). Built by scripts/build_device_library.py.
"""

import json
import random
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "assets" / "devices" / "devices.json"
_OS_KEY = {"windows": "win", "macos": "mac", "linux": "lin"}


@lru_cache(maxsize=1)
def load() -> dict:
    """{"windows": [record, ...], "macos": [...], "linux": [...]}"""
    return json.loads(PATH.read_text(encoding="utf-8"))["presets"]


# The largest panels: a 4K monitor, and Apple's 6016x3384 Pro Display XDR.
PANEL = {"windows": (3840, 2160), "linux": (3840, 2160), "macos": (6016, 3384)}


@lru_cache(maxsize=1)
def host_dpr() -> float:
    """This machine's display scale, which every page sees: Camoufox's DPR override
    changes only the JS value, not media queries or rendering."""
    try:
        from AppKit import NSScreen

        return float(NSScreen.mainScreen().backingScaleFactor())
    except Exception:  # noqa: BLE001
        return 1.0  # ponytail: Windows/Linux scaling not probed; add when run off a Mac


def fits_panel(os: str, width: int, height: int) -> bool:
    """Whether a logical screen at this machine's scale is a real physical panel."""
    w, h = PANEL[os]
    return width * host_dpr() <= w and height * host_dpr() <= h


def pick(os: str, rng: random.Random | None = None) -> dict:
    """A uniformly random record for `os` whose screen fits a real panel at this machine's scale."""
    recs = load()[os]
    fitting = [r for r in recs if fits_panel(os, r["screen"]["width"], r["screen"]["height"])]
    return (rng or random).choice(fitting or recs)


@lru_cache(maxsize=8)
def gpus(os: str) -> list[dict]:
    """Allowed custom WebGL GPUs: Firefox GPUs with recorded WebGL parameters that fit `os`."""
    from camoufox.coherence import gpu_fits_os
    from camoufox.fingerprints import is_software_renderer
    from camoufox.webgl import firefox_gpus

    pairs = sorted(
        (v, r)
        for v, r in firefox_gpus(os)
        if r != "Mozilla" and not is_software_renderer(r) and gpu_fits_os(r, _OS_KEY[os])
    )
    return [{"vendor": v, "renderer": r} for v, r in pairs]


@lru_cache(maxsize=8)
def screens(os: str) -> list[str]:
    """Distinct "WxH" screens seen in the library for `os`, largest first."""
    sizes = {(r["screen"]["width"], r["screen"]["height"]) for r in load()[os]}
    return [f"{w}x{h}" for w, h in sorted(sizes, reverse=True)]
