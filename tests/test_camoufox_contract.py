"""FoxProfile calls and patches a few Camoufox internals.

These tests fail in CI when a Camoufox release changes them, instead of failing
on a user's machine at launch.
"""

import sys
import types

import pytest


def test_locale_selector_exists():
    from camoufox.locales import SELECTOR, normalize_locale

    assert callable(getattr(SELECTOR, "from_region", None))
    assert callable(normalize_locale)


def test_geolocation_and_exit_ip_helpers_exist():
    from camoufox.geolocation import get_geolocation
    from camoufox.ip import public_ip

    assert callable(get_geolocation)
    assert callable(public_ip)


def test_virtual_display_helper_exists():
    from camoufox.virtdisplay import VirtualDisplay

    assert callable(VirtualDisplay)


def test_pinned_locale_replaces_the_geoip_draw(monkeypatch):
    from camoufox.locales import SELECTOR, normalize_locale

    from src.services.browser import runner

    # pin_geoip_locale patches the selector for the whole process: restore it afterwards.
    monkeypatch.setattr(SELECTOR, "from_region", SELECTOR.from_region)
    runner.pin_geoip_locale("vi-VN")
    expected = normalize_locale("vi-VN")
    assert SELECTOR.from_region("VN") == expected
    assert SELECTOR.from_region("US") == expected


def test_a_camoufox_without_the_selector_fails_the_launch(monkeypatch):
    from src.services.browser import runner

    fake = types.ModuleType("camoufox.locales")
    fake.SELECTOR = types.SimpleNamespace()
    fake.normalize_locale = lambda value: value
    monkeypatch.setitem(sys.modules, "camoufox.locales", fake)
    with pytest.raises(runner.CamoufoxIncompatible):
        runner.pin_geoip_locale("vi-VN")
