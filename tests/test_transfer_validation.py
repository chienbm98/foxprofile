"""An archive is user-supplied data: an invalid OS or proxy in it must not be registered."""

import json
import zipfile

import pytest

from src.services.profile.transfer import import_from_zip


def _archive(path, profile_json):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("profile.json", json.dumps(profile_json))
    return str(path)


@pytest.mark.parametrize("os_type", ["amiga", "../windows", ""])
def test_import_rejects_an_unknown_os(tmp_path, os_type):
    zip_path = _archive(tmp_path / "p.zip", {"name": "good", "os_type": os_type})
    ok, msg = import_from_zip(zip_path, str(tmp_path / "data"))
    assert not ok and "OS" in msg


@pytest.mark.parametrize("proxy", ["not a proxy", "host:99999", "http://user:pw@host"])
def test_import_rejects_an_invalid_proxy_in_proxy_mode(tmp_path, proxy):
    zip_path = _archive(
        tmp_path / "p.zip",
        {"name": "good", "os_type": "windows", "proxy_mode": "proxy", "proxy": proxy},
    )
    ok, msg = import_from_zip(zip_path, str(tmp_path / "data"))
    assert not ok and "proxy" in msg.lower()


def test_import_accepts_a_valid_proxy(tmp_path):
    zip_path = _archive(
        tmp_path / "p.zip",
        {
            "name": "good",
            "os_type": "linux",
            "proxy_mode": "proxy",
            "proxy": "socks5://192.0.2.10:1080",
        },
    )
    ok, profile = import_from_zip(zip_path, str(tmp_path / "data"))
    assert ok and profile.proxy == "socks5://192.0.2.10:1080"


def test_a_stored_proxy_is_dropped_outside_proxy_mode(tmp_path):
    zip_path = _archive(
        tmp_path / "p.zip",
        {"name": "good", "os_type": "windows", "proxy_mode": "direct", "proxy": "garbage"},
    )
    ok, profile = import_from_zip(zip_path, str(tmp_path / "data"))
    assert ok and profile.proxy is None
