import json
import zipfile

import pytest

from src.services.browser.launcher import BrowserLauncher, ProfileBusyError, _LaunchResult
from src.services.profile.transfer import import_from_zip


def _archive(path, name, files):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("profile.json", json.dumps({"name": name, "os_type": "windows"}))
        for arcname, data in files.items():
            z.writestr(arcname, data)
    return str(path)


def test_import_rejects_traversal_profile_name(tmp_path):
    zip_path = _archive(tmp_path / "p.zip", "..", {})
    ok, msg = import_from_zip(zip_path, str(tmp_path / "data"))
    assert not ok and "name" in msg


def test_import_rejects_zip_slip_entry(tmp_path):
    zip_path = _archive(tmp_path / "p.zip", "good", {"data/../../escaped.txt": "x"})
    ok, msg = import_from_zip(zip_path, str(tmp_path / "data"))
    assert not ok and "Unsafe path" in msg
    assert not (tmp_path / "escaped.txt").exists()


def test_import_extracts_normal_archive(tmp_path):
    zip_path = _archive(tmp_path / "p.zip", "good", {"data/fingerprint.json": "{}"})
    ok, profile = import_from_zip(zip_path, str(tmp_path / "data"))
    assert ok and profile.name == "good"
    assert (tmp_path / "data" / "good" / "fingerprint.json").read_text() == "{}"


def test_exclusive_blocks_second_holder():
    bl = BrowserLauncher()
    with bl.exclusive("p"), pytest.raises(ProfileBusyError), bl.exclusive("p"):
        pass
    with bl.exclusive("p"):  # released after the block
        pass


def test_launch_result_settles_once():
    r = _LaunchResult()
    r.settle(True)
    r.settle(False, "late failure")
    assert r.ok is True and r.error is None


def test_export_without_data_keeps_the_identity(tmp_path):
    from src.models.profile import Profile
    from src.services.profile.transfer import export_to_zip

    data = tmp_path / "data"
    (data / "Default").mkdir(parents=True)
    for name in ("fingerprint.json", "chrome_persona.json", "geo_locale.json"):
        (data / name).write_text("{}", encoding="utf-8")
    (data / "Default" / "Cookies").write_text("x", encoding="utf-8")
    ok, zip_path = export_to_zip(Profile(name="alice"), str(data), str(tmp_path), False)
    assert ok
    names = set(zipfile.ZipFile(zip_path).namelist())
    assert {"data/fingerprint.json", "data/chrome_persona.json", "data/geo_locale.json"} <= names
    assert "data/Default/Cookies" not in names
