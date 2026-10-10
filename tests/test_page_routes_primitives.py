"""The REST routes for upload, waits, scroll and the compact snapshot forward to the control server."""

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.container import Container


@pytest.fixture
def api(tmp_path, monkeypatch):
    # profiles.json is relative to the working directory, and routes need the profile to exist.
    monkeypatch.chdir(tmp_path)
    container = Container()
    container.profile_manager.add_profile("p", "", "windows")
    calls = []

    def control(name, action, params=None, timeout=60):
        calls.append((name, action, params))
        return {"ok": True}

    monkeypatch.setattr(container.browser_launcher, "control", control)
    return TestClient(create_app(container), base_url="http://127.0.0.1"), calls


@pytest.mark.parametrize(
    ("path", "body", "action", "params"),
    [
        (
            "upload",
            {"selector": "input[type=file]", "paths": ["media_outbox/a.png"]},
            "upload",
            {"selector": "input[type=file]", "paths": ["media_outbox/a.png"], "timeout": 15_000},
        ),
        ("wait-url", {"pattern": "/me"}, "wait_for_url", {"pattern": "/me", "timeout": 15_000}),
        ("wait-text", {"text": "Posted"}, "wait_for_text", {"text": "Posted", "timeout": 15_000}),
        ("scroll", {"to": "bottom"}, "scroll", {"dy": 600, "to": "bottom"}),
    ],
)
def test_routes_forward_action_and_params(api, path, body, action, params):
    client, calls = api
    response = client.post(f"/api/v1/browser/p/page/{path}", json=body)
    assert response.status_code == 200, response.text
    assert calls == [("p", action, params)]


def test_snapshot_forwards_interactive_only(api):
    client, calls = api
    response = client.get("/api/v1/browser/p/page/snapshot", params={"interactive_only": "true"})
    assert response.status_code == 200
    assert calls == [("p", "snapshot", {"max_chars": 40_000, "interactive_only": True})]


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("upload", {"selector": "input", "paths": []}),
        ("scroll", {"to": "middle"}),
        ("wait-text", {"text": "x" * 501}),
    ],
)
def test_invalid_bodies_are_rejected(api, path, body):
    client, calls = api
    assert client.post(f"/api/v1/browser/p/page/{path}", json=body).status_code == 422
    assert calls == []
