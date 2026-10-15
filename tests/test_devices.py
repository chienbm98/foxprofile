import json
import random

import pytest

from src.services.browser import devices

OSES = ("windows", "macos", "linux")


@pytest.mark.parametrize("os_name", OSES)
def test_every_record_gpu_is_allowed(os_name):
    allowed = {(g["vendor"], g["renderer"]) for g in devices.gpus(os_name)}
    assert allowed
    for rec in devices.load()[os_name]:
        assert (rec["webgl"]["unmaskedVendor"], rec["webgl"]["unmaskedRenderer"]) in allowed
        assert rec["screen"]["width"] >= 1280 and rec["screen"]["height"] >= 720


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
