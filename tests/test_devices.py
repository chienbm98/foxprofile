import json
import random

import pytest
from camoufox.coherence import PLAUSIBLE_DPR

from src.services.browser import devices

OSES = ("windows", "macos", "linux")


@pytest.mark.parametrize("os_name", OSES)
def test_every_record_gpu_is_allowed(os_name):
    allowed = {(g["vendor"], g["renderer"]) for g in devices.gpus(os_name)}
    assert allowed
    for rec in devices.load()[os_name]:
        assert (rec["webgl"]["unmaskedVendor"], rec["webgl"]["unmaskedRenderer"]) in allowed
        assert rec["screen"]["width"] >= 1280 and rec["screen"]["height"] >= 720
        scr, nav = rec["screen"], rec["navigator"]
        assert (
            scr["devicePixelRatio"]
            in PLAUSIBLE_DPR[{"windows": "win", "macos": "mac", "linux": "lin"}[os_name]]
        )
        assert nav["maxTouchPoints"] == 0  # Camoufox cannot fake touch events
        if os_name == "macos":
            assert scr["width"] * scr["devicePixelRatio"] <= 6016
            assert rec["webgl"]["unmaskedRenderer"].startswith("Apple") or (
                nav["hardwareConcurrency"] <= 8
            )


@pytest.mark.parametrize("os_name", OSES)
def test_pick_and_screens(os_name):
    rec = devices.pick(os_name, random.Random(1))
    assert rec in devices.load()[os_name]
    assert f"{rec['screen']['width']}x{rec['screen']['height']}" in devices.screens(os_name)
    assert len({r["id"] for r in devices.load()[os_name]}) == len(devices.load()[os_name])


@pytest.mark.parametrize("os_name", OSES)
def test_launch_options_accepts_a_record(os_name):
    from camoufox.exceptions import CamoufoxNotInstalled
    from camoufox.utils import launch_options

    rec = devices.pick(os_name, random.Random(2))
    try:
        opts = launch_options(
            os=os_name, headless=True, fingerprint_preset=rec, i_know_what_im_doing=True
        )
    except CamoufoxNotInstalled:
        pytest.skip("Camoufox browser not fetched (python -m camoufox fetch)")
    env = opts["env"]
    names = sorted(
        (k for k in env if k.startswith("CAMOU_CONFIG_")), key=lambda k: int(k.rsplit("_", 1)[1])
    )
    cfg = json.loads("".join(env[k] for k in names))
    assert cfg["webGl:renderer"] == rec["webgl"]["unmaskedRenderer"]
