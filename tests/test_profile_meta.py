import json

import pytest
from fastapi.testclient import TestClient

from src.services.automation.engine import ActivityLog, Automation
from src.services.browser.session_check import classify
from src.services.profile.manager import ProfileManager


def test_classify_inbox_and_signed_out():
    inbox = classify(
        "https://mail.google.com/mail/u/0/#inbox", "Inbox (3) - Someone.Name@gmail.com - Gmail"
    )
    assert inbox == {"state": "alive", "email": "someone.name@gmail.com"}
    assert classify("https://accounts.google.com/v3/signin/identifier", "Sign in")["state"] == (
        "logged_out"
    )
    assert classify("https://workspace.google.com/intl/ja/gmail/", "Gmail")["state"] == "logged_out"
    assert classify("https://example.com/", "x")["state"] == "unknown"


def test_meta_persists_and_old_files_still_load(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "profiles.json").write_text(
        json.dumps({"old": {"name": "old", "proxy": None, "os_type": "linux"}})
    )
    pm = ProfileManager()
    assert pm.profiles["old"].tags == [] and pm.profiles["old"].email is None
    pm.update_meta("old", email="a@b.co", purpose="free signups", notes="l1\nl2", tags=["z", "a"])
    again = ProfileManager().profiles["old"]
    assert (again.email, again.purpose, again.notes, again.tags) == (
        "a@b.co",
        "free signups",
        "l1\nl2",
        ["a", "z"],
    )
    pm.update_meta("old", email="")
    assert ProfileManager().profiles["old"].email is None
    with pytest.raises(ValueError):
        pm.update_meta("old", proxy="x")


def test_meta_travels_in_profile_zip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pm = ProfileManager()
    pm.add_profile("p", "", "linux")
    pm.update_meta("p", email="a@b.co", tags=["gmail"], purpose="main")
    ok, zip_path = pm.export_profile("p", str(tmp_path))
    assert ok
    pm.delete_profile("p")
    ok, name = pm.import_profile(zip_path)
    assert ok and pm.profiles[name].email == "a@b.co" and pm.profiles[name].tags == ["gmail"]


def test_api_create_update_and_validate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from src.api.app import create_app
    from src.core.container import Container

    with TestClient(create_app(Container()), base_url="http://127.0.0.1:8000") as c:
        made = c.post(
            "/api/v1/profiles",
            json={"name": "g1", "email": "me@gmail.com", "tags": ["gmail"], "purpose": "main"},
        )
        assert made.status_code == 201
        assert made.json()["email"] == "me@gmail.com" and made.json()["tags"] == ["gmail"]
        patched = c.patch("/api/v1/profiles/g1", json={"notes": "a\nb", "tags": ["x", "y"]})
        assert patched.json()["notes"] == "a\nb" and patched.json()["email"] == "me@gmail.com"
        renamed = c.patch("/api/v1/profiles/g1", json={"name": "g2"})
        assert renamed.json()["tags"] == ["x", "y"]
        bad = c.patch("/api/v1/profiles/g2", json={"email": "nope"})
        assert bad.status_code == 400
        assert (
            c.post("/api/v1/profiles", json={"name": "g3", "tags": ["a" * 40]}).status_code == 400
        )


class _PM:
    def __init__(self):
        self.profiles = {"a": object()}
        self.meta = {}

    def update_meta(self, name, **fields):
        self.meta.update(fields)
        return True


class _Launcher:
    def __init__(self):
        self.running = set()
        self.title = "Inbox - x@gmail.com - Gmail"

    def is_running(self, n):
        return n in self.running

    def start_thread(self, profile, log, **kw):
        return True

    def wait_for_launch(self, n, t):
        self.running.add(n)
        return True, None

    def stop_profile(self, n, timeout=2):
        self.running.discard(n)

    def control(self, n, action, params=None, timeout=60):
        if action == "evaluate":
            return {
                "result": {"url": "https://mail.google.com/mail/u/0/#inbox", "title": self.title}
            }
        return {}


def test_check_session_records_state_and_closes_profile(tmp_path, monkeypatch):
    monkeypatch.setattr("src.services.browser.session_check.time.sleep", lambda s: None)
    pm, la = _PM(), _Launcher()
    a = Automation(pm, la, path=str(tmp_path / "a.json"), log=ActivityLog(str(tmp_path / "l")))
    assert a.check_session("a") == {"state": "alive", "email": "x@gmail.com"}
    assert pm.meta["session_state"] == "alive" and pm.meta["email"] == "x@gmail.com"
    assert pm.meta["session_checked_at"] > 0
    assert not la.running
