"""Profile operations keep a running browser's data and the saved state safe.

Destructive operations refuse a profile whose browser is running, and a failed
write of profiles.json rolls the change back instead of reporting success.
"""

import contextlib
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core import config
from src.core.container import Container
from src.core.errors import ProfileBusyError, ProfileStoreError
from src.services.profile import manager as manager_module
from src.services.profile.manager import ProfileManager


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # logs/ and the default relative paths live here
    monkeypatch.setattr(config, "PROFILES_FILE", str(tmp_path / "profiles.json"))
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(config, "PROTON_ACCOUNTS_FILE", str(tmp_path / "proton_accounts.json"))
    monkeypatch.setattr(config, "PROTON_ACCOUNTS_KEY_FILE", str(tmp_path / "proton_accounts.key"))
    return tmp_path


class _Running:
    """Stands in for BrowserLauncher.exclusive: refuses names whose browser runs."""

    def __init__(self) -> None:
        self.names: set[str] = set()

    @contextlib.contextmanager
    def __call__(self, name):
        if name in self.names:
            raise ProfileBusyError(name)
        yield


def _manager():
    running = _Running()
    return ProfileManager(exclusive=running), running


def _seed_data(store, name, content="LIVE"):
    folder = store / "data" / name
    folder.mkdir(parents=True, exist_ok=True)
    cookies = folder / "cookies.sqlite"
    cookies.write_text(content, encoding="utf-8")
    return cookies


def _archive(path, name, files):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(
            "profile.json",
            json.dumps({"name": name, "os_type": "windows", "engine": "camoufox"}),
        )
        for arcname, data in files.items():
            z.writestr(arcname, data)
    return str(path)


def _break_profile_writes(monkeypatch):
    def disk_full(_src, _dst, attempts=10):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(manager_module, "_replace", disk_full)


# --- a running browser is never touched -----------------------------------------------


def test_delete_is_refused_while_the_browser_runs(store):
    pm, running = _manager()
    pm.add_profile("p", "", "windows")
    cookies = _seed_data(store, "p")
    running.names.add("p")

    with pytest.raises(ProfileBusyError):
        pm.delete_profile("p")
    assert "p" in pm.profiles
    assert cookies.read_text(encoding="utf-8") == "LIVE"


def test_rename_is_refused_while_the_browser_runs(store):
    pm, running = _manager()
    pm.add_profile("p", "", "windows")
    cookies = _seed_data(store, "p")
    running.names.add("p")

    with pytest.raises(ProfileBusyError):
        pm.update_profile("p", "q", "", "windows")
    assert (store / "data" / "p").is_dir()
    assert not (store / "data" / "q").exists()
    assert cookies.read_text(encoding="utf-8") == "LIVE"


def test_export_with_data_is_refused_while_the_browser_runs(store, tmp_path):
    pm, running = _manager()
    pm.add_profile("p", "", "windows")
    _seed_data(store, "p")
    running.names.add("p")
    out = tmp_path / "out"
    out.mkdir()

    with pytest.raises(ProfileBusyError):
        pm.export_profile("p", str(out), include_data=True)
    ok, path = pm.export_profile("p", str(out), include_data=False)
    assert ok and path.endswith(".zip")


def test_overwriting_import_is_refused_while_the_browser_runs(store, tmp_path):
    pm, running = _manager()
    pm.add_profile("p", "", "windows")
    cookies = _seed_data(store, "p")
    archive = _archive(tmp_path / "in.zip", "p", {"data/cookies.sqlite": "OVERWRITE"})
    running.names.add("p")

    with pytest.raises(ProfileBusyError):
        pm.import_profile(archive, overwrite=True)
    assert cookies.read_text(encoding="utf-8") == "LIVE"


# --- a failed save is reported and rolled back -------------------------------------------


def test_failed_save_rolls_back_a_new_profile(store, monkeypatch):
    pm, _ = _manager()
    _break_profile_writes(monkeypatch)

    with pytest.raises(ProfileStoreError, match="Could not write profiles.json"):
        pm.add_profile("p", "", "windows")
    assert "p" not in pm.profiles


def test_failed_save_rolls_back_an_edit(store, monkeypatch):
    pm, _ = _manager()
    pm.add_profile("p", "", "windows")
    _break_profile_writes(monkeypatch)

    with pytest.raises(ProfileStoreError):
        pm.update_profile("p", "p", "", "linux")
    assert pm.profiles["p"].os_type == "windows"


def test_failed_save_keeps_the_data_of_a_profile_that_was_not_deleted(store, monkeypatch):
    pm, _ = _manager()
    pm.add_profile("p", "", "windows")
    cookies = _seed_data(store, "p")
    _break_profile_writes(monkeypatch)

    with pytest.raises(ProfileStoreError):
        pm.delete_profile("p")
    assert "p" in pm.profiles
    assert cookies.read_text(encoding="utf-8") == "LIVE"


def test_failed_save_moves_a_renamed_data_dir_back(store, monkeypatch):
    pm, _ = _manager()
    pm.add_profile("p", "", "windows")
    cookies = _seed_data(store, "p")
    _break_profile_writes(monkeypatch)

    with pytest.raises(ProfileStoreError):
        pm.update_profile("p", "q", "", "windows")
    assert "p" in pm.profiles and "q" not in pm.profiles
    assert cookies.read_text(encoding="utf-8") == "LIVE"


def test_a_corrupt_profiles_file_is_kept_before_a_save_replaces_it(store):
    path = store / "profiles.json"
    path.write_text("{broken", encoding="utf-8")

    pm, _ = _manager()
    assert pm.profiles == {}
    backups = list(store.glob("profiles.json.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{broken"

    pm.add_profile("p", "", "windows")
    assert "p" in json.loads(path.read_text(encoding="utf-8"))


# --- the API reports these outcomes ----------------------------------------------------


class _FakeProcess:
    """A browser process that has not exited, as far as the launcher can tell."""

    def poll(self):
        return None

    def terminate(self):
        pass

    def kill(self):
        pass

    def wait(self, timeout=None):
        return 0


@pytest.fixture
def client(store):
    return TestClient(create_app(Container()), base_url="http://127.0.0.1")


def _mark_running(client, name):
    client.app.state.container.browser_launcher._active_sessions[name] = _FakeProcess()


def test_api_refuses_an_overwriting_import_over_a_running_profile(client, store, tmp_path):
    client.app.state.container.profile_manager.add_profile("p", "", "windows")
    cookies = _seed_data(store, "p")
    archive = _archive(tmp_path / "in.zip", "p", {"data/cookies.sqlite": "OVERWRITE"})
    _mark_running(client, "p")

    response = client.post("/api/v1/profiles/import", json={"zip_path": archive, "overwrite": True})
    assert response.status_code == 409
    assert cookies.read_text(encoding="utf-8") == "LIVE"


def test_api_refuses_an_export_with_data_while_the_browser_runs(client, store, tmp_path):
    client.app.state.container.profile_manager.add_profile("p", "", "windows")
    _seed_data(store, "p")
    out = tmp_path / "out"
    out.mkdir()
    _mark_running(client, "p")

    response = client.post(
        "/api/v1/profiles/p/export", json={"export_dir": str(out), "include_data": True}
    )
    assert response.status_code == 409


def test_api_reports_a_failed_save_as_an_error(client, store, monkeypatch):
    _break_profile_writes(monkeypatch)

    response = client.post("/api/v1/profiles", json={"name": "p", "os_type": "windows"})
    assert response.status_code == 500
    assert "Could not write profiles.json" in response.json()["detail"]
    assert client.get("/api/v1/profiles").json()["total"] == 0


def test_api_lists_profiles_when_the_accounts_file_is_corrupt(client, store):
    client.app.state.container.profile_manager.add_profile("p", "", "windows")
    (store / "proton_accounts.json").write_text("{not json", encoding="utf-8")

    response = client.get("/api/v1/profiles")
    assert response.status_code == 200
    assert [p["name"] for p in response.json()["profiles"]] == ["p"]
