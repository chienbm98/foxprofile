import json

import pytest

from src.services.browser import fingerprint


@pytest.fixture
def fake_freeze(monkeypatch):
    """Replace the camoufox resolve step so tests need no browser."""
    calls = []

    def freeze(os_type):
        calls.append(os_type)
        device = {
            "navigator.platform": f"{os_type}-{len(calls)}",
            "navigator.hardwareConcurrency": 8,
            "screen.width": 1920,
            "screen.height": 1080,
            "webGl:renderer": "Test GPU",
            "window.devicePixelRatio": 1.5,
        }
        return f"rec-{len(calls)}", device

    monkeypatch.setattr(fingerprint, "_freeze", freeze)
    return calls


def test_first_load_freezes_and_saves(tmp_path, fake_freeze):
    device = fingerprint.load_or_create(str(tmp_path), "windows")
    assert fake_freeze == ["windows"]
    saved = json.loads((tmp_path / "fingerprint.json").read_text(encoding="utf-8"))
    assert saved == {"version": 2, "os": "windows", "source": "rec-1", "device": device}
    assert fingerprint.load_saved(str(tmp_path)) == device


def test_second_load_reuses_saved(tmp_path, fake_freeze):
    first = fingerprint.load_or_create(str(tmp_path), "windows")
    assert fingerprint.load_or_create(str(tmp_path), "windows") == first
    assert fake_freeze == ["windows"]


def test_old_device_without_dpr_gets_a_common_one(tmp_path, fake_freeze):
    fingerprint.load_or_create(str(tmp_path), "windows")
    path = tmp_path / "fingerprint.json"
    data = json.loads(path.read_text())
    del data["device"]["window.devicePixelRatio"]
    path.write_text(json.dumps(data))
    assert fingerprint.load_or_create(str(tmp_path), "windows")["window.devicePixelRatio"] == 1


def test_os_change_regenerates(tmp_path, fake_freeze):
    fingerprint.load_or_create(str(tmp_path), "windows")
    mac = fingerprint.load_or_create(str(tmp_path), "macos")
    assert fake_freeze == ["windows", "macos"]
    assert mac["navigator.platform"].startswith("macos")


def test_v1_file_regenerates(tmp_path, fake_freeze):
    (tmp_path / "fingerprint.json").write_text(
        json.dumps({"os": "linux", "fingerprint": {"navigator": {}}}), encoding="utf-8"
    )
    assert fingerprint.load_saved(str(tmp_path)) is None
    assert fingerprint.summary(str(tmp_path)) is None
    fingerprint.load_or_create(str(tmp_path), "linux")
    assert fake_freeze == ["linux"]


def test_corrupt_file_regenerates(tmp_path, fake_freeze):
    (tmp_path / "fingerprint.json").write_text("{broken", encoding="utf-8")
    fingerprint.load_or_create(str(tmp_path), "linux")
    assert fake_freeze == ["linux"]


def test_reset_and_summary(tmp_path, fake_freeze):
    assert fingerprint.summary(str(tmp_path)) is None
    fingerprint.load_or_create(str(tmp_path), "windows")
    assert fingerprint.summary(str(tmp_path)) == {
        "os": "windows",
        "platform": "windows-1",
        "screen": "1920x1080",
        "hardware_concurrency": 8,
        "webgl_renderer": "Test GPU",
        "source": "rec-1",
    }
    assert fingerprint.reset(str(tmp_path)) is True
    assert fingerprint.reset(str(tmp_path)) is False
    assert fingerprint.summary(str(tmp_path)) is None


def test_decode_config_joins_chunks():
    env = {"CAMOU_CONFIG_2": '"b": 2}', "CAMOU_CONFIG_1": '{"a": 1, ', "PATH": "/bin"}
    assert fingerprint.decode_config(env) == {"a": 1, "b": 2}
