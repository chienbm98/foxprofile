"""The browser engine a profile runs on: stored, validated, and routed to its runner."""

import json
import sys

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.container import Container
from src.models.profile import Profile
from src.services.browser import fingerprint
from src.services.browser.process import runner_command
from src.services.profile.manager import ProfileManager


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    # profiles.json, camoufox_data/ and logs/ are relative to the working directory.
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def client(workdir):
    # The token-less API only answers loopback Host headers.
    return TestClient(create_app(Container()), base_url="http://127.0.0.1")


def test_engine_defaults_to_camoufox_for_old_profiles(workdir):
    (workdir / "profiles.json").write_text(
        json.dumps({"old": {"name": "old", "proxy": None, "os_type": "macos"}}), encoding="utf-8"
    )
    assert ProfileManager().profiles["old"].engine == "camoufox"


def test_unknown_engine_in_profiles_file_falls_back(workdir):
    (workdir / "profiles.json").write_text(
        json.dumps({"x": {"name": "x", "os_type": "linux", "engine": "netscape"}}),
        encoding="utf-8",
    )
    assert ProfileManager().profiles["x"].engine == "camoufox"


def test_engine_survives_save_and_reload(workdir):
    ProfileManager().add_profile("c", "", "macos", engine="chrome")
    assert ProfileManager().profiles["c"].engine == "chrome"


def test_runner_command_follows_the_engine():
    camoufox = runner_command(Profile(name="a", os_type="windows"))
    chrome = runner_command(Profile(name="b", proxy="1.2.3.4:80", os_type="macos", engine="chrome"))
    assert camoufox[0] == chrome[0] == sys.executable
    assert camoufox[1].endswith("runner.py")
    assert chrome[1:3] == ["-m", "chrome_engine.runner"]
    # Same positional protocol for both runners.
    assert chrome[3:] == ["b", "1.2.3.4:80", "macos", "", ""]


def test_api_creates_and_reports_the_engine(client):
    r = client.post("/api/v1/profiles", json={"name": "c1", "os_type": "macos", "engine": "chrome"})
    assert r.status_code == 201
    assert r.json()["engine"] == "chrome"
    assert client.get("/api/v1/profiles/c1").json()["engine"] == "chrome"
    assert client.post("/api/v1/profiles", json={"name": "f1"}).json()["engine"] == "camoufox"


def test_api_rejects_unknown_engine(client):
    r = client.post("/api/v1/profiles", json={"name": "x", "engine": "netscape"})
    assert r.status_code == 400


def test_api_refuses_to_change_the_engine(client):
    client.post("/api/v1/profiles", json={"name": "c2", "engine": "chrome"})
    r = client.patch("/api/v1/profiles/c2", json={"engine": "camoufox"})
    assert r.status_code == 400
    # Sending the current value along with other edits is fine.
    r = client.patch("/api/v1/profiles/c2", json={"engine": "chrome", "proxy": "1.2.3.4:8080"})
    assert r.status_code == 200
    assert r.json()["engine"] == "chrome"


def test_fingerprint_summary_reads_the_chrome_persona(tmp_path):
    (tmp_path / fingerprint.CHROME_PERSONA_FILE).write_text(
        json.dumps({"seed": 7, "platform": "macos", "hardware_concurrency": 12}), encoding="utf-8"
    )
    assert fingerprint.summary(str(tmp_path)) == {
        "os": "macos",
        "platform": "MacIntel",
        "screen": "1920x1080",
        "hardware_concurrency": 12,
    }
    assert fingerprint.reset(str(tmp_path))
    assert not (tmp_path / fingerprint.CHROME_PERSONA_FILE).exists()
    assert fingerprint.summary(str(tmp_path)) is None


def test_prefetch_skips_an_installed_engine(monkeypatch):
    from src.services.browser import chrome_prefetch

    monkeypatch.setattr(chrome_prefetch, "is_installed", lambda: True)
    assert chrome_prefetch.start() is False


def test_prefetch_runs_once_at_a_time(monkeypatch):
    import threading

    from chrome_engine import fetch
    from src.services.browser import chrome_prefetch

    release = threading.Event()
    calls = []

    def fake_install():
        calls.append(1)
        release.wait(5)

    monkeypatch.setattr(chrome_prefetch, "is_installed", lambda: False)
    monkeypatch.setattr(fetch, "install", fake_install)
    logs = []
    assert chrome_prefetch.start(logs.append) is True
    assert chrome_prefetch.start(logs.append) is False
    release.set()
    chrome_prefetch._thread.join(5)
    assert calls == [1]
    assert len(logs) == 2  # downloading..., ready
