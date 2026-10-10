"""The automation client launches a stopped profile and waits until its pages answer."""

import pytest

from src.mcp_server.server import FoxProfileError
from tqd_automation import client


@pytest.fixture
def api(monkeypatch):
    calls = []
    state = {"running": False, "tabs_failures": 0, "launch_error": None}

    def request(method, path, body=None, query=None, raw=False):
        calls.append((method, path, body, query))
        if path.endswith("/status"):
            return {"is_running": state["running"]}
        if path.endswith("/launch"):
            if state["launch_error"]:
                raise FoxProfileError(state["launch_error"])
            return {"success": True}
        if path.endswith("/tabs"):
            if state["tabs_failures"]:
                state["tabs_failures"] -= 1
                raise FoxProfileError("FoxProfile API 409: Browser is not running")
            return {"tabs": []}
        if path.endswith("/screenshot"):
            return {"png_base64": "iVBORw=="}
        return {"ok": True}

    monkeypatch.setattr(client.server, "_request", request)
    monkeypatch.setattr(client.time, "sleep", lambda s: None)
    return calls, state


def test_running_profile_is_not_launched_again(api):
    calls, state = api
    state["running"] = True
    client.Browser("fb").ensure_running()
    assert [c[1] for c in calls] == ["/browser/fb/status", "/browser/fb/page/tabs"]


def test_stopped_profile_is_launched_then_polled_until_ready(api):
    calls, state = api
    state["tabs_failures"] = 2
    client.Browser("fb").ensure_running()
    paths = [c[1] for c in calls]
    assert paths[:2] == ["/browser/fb/status", "/browser/fb/launch"]
    assert paths.count("/browser/fb/page/tabs") == 3


def test_launch_failure_is_raised(api):
    _, state = api
    state["launch_error"] = "FoxProfile API 502: Launch failed: proxy"
    with pytest.raises(FoxProfileError, match="502"):
        client.Browser("fb").ensure_running()


def test_concurrent_launch_is_tolerated_but_busy_profile_is_not(api):
    calls, state = api
    state["launch_error"] = "FoxProfile API 409: Browser already running"
    client.Browser("fb").ensure_running()
    state["launch_error"] = "FoxProfile API 409: Profile is busy"
    with pytest.raises(FoxProfileError, match="busy"):
        client.Browser("fb").ensure_running()


def test_not_ready_in_time_raises(api, monkeypatch):
    _, state = api
    state["running"] = True
    state["tabs_failures"] = 10**6
    with pytest.raises(FoxProfileError, match="not ready after 0s"):
        client.Browser("fb").ensure_running(timeout=0)


def test_actions_hit_page_routes(api):
    calls, _ = api
    b = client.Browser("fb")
    b.upload("input[type=file]", ["media_outbox/a.png"])
    b.snapshot(interactive_only=True)
    assert b.screenshot_png().startswith(b"\x89PNG")
    assert calls[0][:3] == (
        "POST",
        "/browser/fb/page/upload",
        {"selector": "input[type=file]", "paths": ["media_outbox/a.png"]},
    )
    assert calls[1][3] == {"interactive_only": "true"}
    assert calls[2][3] == {"format": "json"}
