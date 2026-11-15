"""The browser engine a profile runs on: stored, validated, and routed to its runner."""

import json
import sys

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core import config
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
def client(workdir, monkeypatch):
    from src.services.browser import chrome_prefetch

    # Creating a Chrome profile must not start a real ~150 MB download in tests.
    monkeypatch.setattr(chrome_prefetch, "start", lambda log=None: False)
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


def test_proton_mode_survives_save_and_reload(workdir, monkeypatch):
    monkeypatch.setattr(config, "PROTON_ACCOUNTS_FILE", str(workdir / "proton_accounts.json"))
    monkeypatch.setattr(config, "PROTON_ACCOUNTS_KEY_FILE", str(workdir / "proton_accounts.key"))
    ProfileManager().add_profile(
        "e",
        "",
        "macos",
        proxy_mode="proton",
        proton_user="user@example.com",
        proton_password="secret",
    )
    profile = ProfileManager().profiles["e"]
    assert profile.proxy_mode == "proton"
    assert profile.extension == "proton-vpn"
    assert profile.proxy is None


def test_an_old_extension_field_implies_proton_mode(workdir):
    (workdir / "profiles.json").write_text(
        json.dumps({"x": {"name": "x", "os_type": "linux", "extension": "proton-vpn"}}),
        encoding="utf-8",
    )
    profile = ProfileManager().profiles["x"]
    assert profile.proxy_mode == "proton"
    assert profile.extension == "proton-vpn"


def test_unknown_mode_in_profiles_file_falls_back(workdir):
    (workdir / "profiles.json").write_text(
        json.dumps({"x": {"name": "x", "os_type": "linux", "proxy_mode": "nope"}}),
        encoding="utf-8",
    )
    assert ProfileManager().profiles["x"].proxy_mode == "direct"


def test_runner_command_follows_the_engine():
    camoufox = runner_command(Profile(name="a", os_type="windows"))
    chrome = runner_command(
        Profile(name="b", proxy="192.0.2.1:80", os_type="macos", engine="chrome")
    )
    assert camoufox[0] == chrome[0] == sys.executable
    assert camoufox[1].endswith("runner.py")
    assert chrome[1:3] == ["-m", "chrome_engine.runner"]
    # Same positional protocol for both runners.
    assert chrome[3:] == ["b", "192.0.2.1:80", "macos", "", "", "", ""]


def test_runner_command_passes_the_extension():
    cmd = runner_command(Profile(name="e", extension="proton-vpn", proxy_mode="proton"))
    assert cmd[2:] == ["e", "None", "windows", "", "", "proton-vpn", ""]


def test_api_creates_and_reports_proton_mode(client, workdir, monkeypatch):
    monkeypatch.setattr(config, "PROTON_ACCOUNTS_FILE", str(workdir / "proton_accounts.json"))
    monkeypatch.setattr(config, "PROTON_ACCOUNTS_KEY_FILE", str(workdir / "proton_accounts.key"))
    response = client.post(
        "/api/v1/profiles",
        json={
            "name": "p1",
            "proxy_mode": "proton",
            "proton_user": "user@example.com",
            "proton_password": "secret",
            "proton_totp": "TOTP",
            "proton_country": "US",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["proxy_mode"] == "proton"
    assert body["extension"] == "proton-vpn"
    assert body["proton_user"] == "user@example.com"
    assert body["has_proton_password"] is True
    assert body["proton_totp_set"] is True
    assert body["proton_country"] == "US"
    assert "secret" not in response.text
    assert client.get("/api/v1/profiles/p1").json()["proxy_mode"] == "proton"
    assert client.post("/api/v1/profiles", json={"name": "p2"}).json()["proxy_mode"] == "direct"


def test_api_rejects_an_unknown_country(client):
    response = client.post(
        "/api/v1/profiles",
        json={
            "name": "p-country",
            "proxy_mode": "proton",
            "proton_user": "u",
            "proton_password": "p",
            "proton_country": "ZZ",
        },
    )
    assert response.status_code == 400


def test_proton_countries_endpoint(client):
    countries = client.get("/api/v1/proton/countries").json()
    assert {"code": "US", "name": "United States"} in countries
    assert len(countries) > 100


def test_api_rejects_an_unknown_proxy_mode(client):
    response = client.post("/api/v1/profiles", json={"name": "p3", "proxy_mode": "ublock"})
    assert response.status_code == 400


def test_api_switches_connection_modes(client, workdir, monkeypatch):
    monkeypatch.setattr(config, "PROTON_ACCOUNTS_FILE", str(workdir / "proton_accounts.json"))
    monkeypatch.setattr(config, "PROTON_ACCOUNTS_KEY_FILE", str(workdir / "proton_accounts.key"))
    client.post(
        "/api/v1/profiles",
        json={
            "name": "p4",
            "proxy_mode": "proton",
            "proton_user": "user@example.com",
            "proton_password": "secret",
        },
    )
    # Switching to direct removes the extension but keeps the saved account
    # so switching back does not need the password again.
    body = client.patch("/api/v1/profiles/p4", json={"proxy_mode": "direct"}).json()
    assert body["proxy_mode"] == "direct"
    assert body["extension"] is None
    body = client.patch("/api/v1/profiles/p4", json={"proxy_mode": "proton"}).json()
    assert body["proxy_mode"] == "proton"
    assert body["has_proton_password"] is True

    body = client.patch(
        "/api/v1/profiles/p4", json={"proxy_mode": "proxy", "proxy": "192.0.2.1:8080"}
    ).json()
    assert body["proxy_mode"] == "proxy"
    assert body["proxy"] == "192.0.2.1:8080"
    # Editing the proxy without a mode keeps proxy mode.
    body = client.patch("/api/v1/profiles/p4", json={"proxy": "198.51.100.5:80"}).json()
    assert body["proxy_mode"] == "proxy"


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
    r = client.patch("/api/v1/profiles/c2", json={"engine": "chrome", "proxy": "192.0.2.1:8080"})
    assert r.status_code == 200
    assert r.json()["engine"] == "chrome"


def test_fingerprint_summary_reads_the_chrome_persona(tmp_path):
    (tmp_path / fingerprint.CHROME_PERSONA_FILE).write_text(
        json.dumps({"seed": 7, "platform": "macos", "hardware_concurrency": 12}), encoding="utf-8"
    )
    assert fingerprint.summary(str(tmp_path)) == {
        "os": "macos",
        "platform": "MacIntel",
        "screen": None,
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


def test_api_refuses_chrome_on_an_unsupported_host(client, monkeypatch):
    from src.services.browser import chrome_prefetch

    monkeypatch.setattr(chrome_prefetch, "unsupported_reason", lambda: "no build for darwin/x86_64")
    r = client.post("/api/v1/profiles", json={"name": "c3", "engine": "chrome"})
    assert r.status_code == 400
    assert "darwin/x86_64" in r.json()["detail"]
