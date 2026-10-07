import json
import sys
import types

import pytest

from src.services.browser import fingerprint


@pytest.fixture
def fake_generator(monkeypatch):
    """Replace camoufox's generator so tests need no browser or model download."""
    calls = []

    def generate_fingerprint(os=None):
        calls.append(os)
        return {
            "navigator": {"platform": f"{os}-{len(calls)}", "hardwareConcurrency": 8},
            "screen": {"width": 1920, "height": 1080},
        }

    module = types.ModuleType("camoufox.fingerprints")
    module.generate_fingerprint = generate_fingerprint
    monkeypatch.setitem(sys.modules, "camoufox.fingerprints", module)
    return calls


def test_first_load_generates_and_saves(tmp_path, fake_generator):
    fp = fingerprint.load_or_create(str(tmp_path), "windows")
    assert fake_generator == ["windows"]
    saved = json.loads((tmp_path / "fingerprint.json").read_text(encoding="utf-8"))
    assert saved == {"os": "windows", "fingerprint": fp}


def test_second_load_reuses_saved(tmp_path, fake_generator):
    first = fingerprint.load_or_create(str(tmp_path), "windows")
    second = fingerprint.load_or_create(str(tmp_path), "windows")
    assert first == second
    assert fake_generator == ["windows"]


def test_os_change_regenerates(tmp_path, fake_generator):
    fingerprint.load_or_create(str(tmp_path), "windows")
    mac = fingerprint.load_or_create(str(tmp_path), "macos")
    assert fake_generator == ["windows", "macos"]
    assert mac["navigator"]["platform"].startswith("macos")


def test_corrupt_file_regenerates(tmp_path, fake_generator):
    (tmp_path / "fingerprint.json").write_text("{broken", encoding="utf-8")
    fingerprint.load_or_create(str(tmp_path), "linux")
    assert fake_generator == ["linux"]


def test_reset_and_summary(tmp_path, fake_generator):
    assert fingerprint.summary(str(tmp_path)) is None
    fingerprint.load_or_create(str(tmp_path), "windows")
    assert fingerprint.summary(str(tmp_path)) == {
        "os": "windows",
        "platform": "windows-1",
        "screen": "1920x1080",
        "hardware_concurrency": 8,
    }
    assert fingerprint.reset(str(tmp_path)) is True
    assert fingerprint.reset(str(tmp_path)) is False
    assert fingerprint.summary(str(tmp_path)) is None
