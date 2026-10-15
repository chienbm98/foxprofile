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


def pick(os: str, rng: random.Random | None = None) -> dict:
    """A uniformly random record for `os`."""
    return (rng or random).choice(load()[os])


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
