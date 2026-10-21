import time

import pytest
from fastapi.testclient import TestClient

from src.services.automation.engine import ActivityLog, Automation, AutomationError, validate_steps


class _PM:
    def __init__(self, names):
        self.profiles = dict.fromkeys(names, object())


class _Launcher:
    def __init__(self):
        self.running = set()
        self.calls = []

    def is_running(self, n):
        return n in self.running

    def start_thread(self, profile, log, **kw):
        return True

    def wait_for_launch(self, n, t):
        self.running.add(n)
        return True, None

    def stop_profile(self, n, timeout=2):
        self.running.discard(n)
        return True

    def control(self, n, action, params=None, timeout=60):
        self.calls.append((n, action, params))
        return {"ok": True}


@pytest.fixture
def auto(tmp_path, monkeypatch):
    monkeypatch.setattr("src.services.automation.engine.SCREENSHOT_DIR", str(tmp_path / "s"))
    la = _Launcher()
    a = Automation(
        _PM(["a", "b"]),
        la,
        path=str(tmp_path / "auto.json"),
        log=ActivityLog(str(tmp_path / "act.jsonl")),
    )
    return a, la


def test_validate_steps():
    with pytest.raises(AutomationError):
        validate_steps([])
    with pytest.raises(AutomationError):
        validate_steps([{"do": "explode"}])
    with pytest.raises(AutomationError):
        validate_steps([{"do": "goto"}])
    assert validate_steps([{"do": "wait", "seconds": [1, 2]}])


def test_groups_and_targets(auto):
    a, _ = auto
    with pytest.raises(AutomationError):
        a.set_group("g", ["nope"])
    a.set_group("g", ["b", "a"])
    t = a.create_task("t", steps=[{"do": "scroll"}], group="g", profiles=["a"])
    assert a.targets(t) == ["a", "b"]


def test_run_task_launches_runs_stops(auto):
    a, la = auto
    t = a.create_task("t", steps=[{"do": "goto", "url": "https://x.test"}], profiles=["a", "b"])
    res = a.run_task(t["id"], wait=True)
    assert res == {"a": "ok", "b": "ok"}
    assert ("a", "navigate", {"url": "https://x.test"}) in la.calls
    assert not la.running
    saved = a.tasks()[0]
    assert saved["last_status"] == "ok" and saved["last_run"]
    assert any(e["event"] == "task_end" for e in a.log.tail())


def test_keeps_already_running_profile_open(auto):
    a, la = auto
    la.running.add("a")
    t = a.create_task("t", steps=[{"do": "scroll"}], profiles=["a"])
    a.run_task(t["id"], wait=True)
    assert "a" in la.running


def test_schedule_tick(auto):
    a, _ = auto
    t = a.create_task("t", steps=[{"do": "scroll"}], profiles=["a"], every_minutes=5)
    assert a.tick() == []
    assert a.tick(now=time.time() + 301) == [t["id"]]
    with pytest.raises(AutomationError):
        a.create_task("x", steps=[{"do": "scroll"}], profiles=["a"], daily_at="25:00")


def test_template_and_api(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from src.api.app import create_app
    from src.core.container import Container

    with TestClient(create_app(Container()), base_url="http://127.0.0.1:8000") as client:
        r = client.post(
            "/api/v1/automation/tasks",
            json={
                "name": "k",
                "template": "keepalive-gmail",
                "profiles": ["x"],
                "every_minutes": 60,
            },
        )
        assert r.status_code == 200 and len(r.json()["steps"]) > 3
        assert client.get("/api/v1/automation/tasks").json()["tasks"][0]["name"] == "k"
        bad = client.post(
            "/api/v1/automation/tasks", json={"name": "k", "steps": [{"do": "bad"}], "group": "g"}
        )
        assert bad.status_code == 400
        assert client.get("/api/v1/sync").status_code == 400
