import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from src.api import auth

TOKEN = "t" * 32


def _client(monkeypatch, token):
    monkeypatch.setattr(auth, "API_TOKEN", token)
    app = FastAPI()

    @app.get("/secret", dependencies=[Depends(auth.require_token)])
    def secret():
        return {"ok": True}

    return TestClient(app)


def test_no_token_configured_allows_requests(monkeypatch):
    assert _client(monkeypatch, "").get("/secret").status_code == 200


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ({}, 401),
        ({"Authorization": "Bearer wrong"}, 401),
        ({"Authorization": f"Bearer {TOKEN}"}, 200),
        ({"Authorization": f"bearer {TOKEN}"}, 200),
        ({"X-API-Key": TOKEN}, 200),
        ({"X-API-Key": "wrong"}, 401),
    ],
)
def test_token_required(monkeypatch, headers, status):
    assert _client(monkeypatch, TOKEN).get("/secret", headers=headers).status_code == status


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", ""])
def test_loopback_without_token_is_allowed(host):
    auth.check_bind_safety(host, "")


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5", "::", "my-vps.example.com"])
def test_public_bind_without_token_refused(host):
    with pytest.raises(SystemExit):
        auth.check_bind_safety(host, "")


def test_short_token_refused():
    with pytest.raises(SystemExit):
        auth.check_bind_safety("0.0.0.0", "short")
    auth.check_bind_safety("0.0.0.0", TOKEN)


def test_mcp_server_registers_expected_tools():
    import asyncio

    from src.mcp_server.server import mcp

    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {
        "list_profiles",
        "launch_profile",
        "browser_navigate",
        "browser_snapshot",
        "browser_click",
        "browser_screenshot",
    } <= names
    assert "delete_profile" not in names  # deliberately not exposed to agents


def _guarded_client():
    from src.api.guard import LocalOnlyGuard

    app = FastAPI()
    app.add_middleware(LocalOnlyGuard)

    @app.post("/launch")
    def launch():
        return {"ok": True}

    return TestClient(app)


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ({"Host": "127.0.0.1:8000"}, 200),
        ({"Host": "localhost:8000"}, 200),
        ({"Host": "[::1]:8000"}, 200),
        ({"Host": "127.0.0.1:8000", "Origin": "http://127.0.0.1:8000"}, 200),
        ({"Host": "evil.example.com:8000"}, 403),  # DNS rebinding
        ({"Host": "127.0.0.1.evil.com"}, 403),
        ({"Host": "127.0.0.1:8000", "Origin": "https://evil.example.com"}, 403),  # CSRF
        ({"Host": "127.0.0.1:8000", "Origin": "null"}, 403),  # sandboxed iframe / file page
    ],
)
def test_local_only_guard(headers, status):
    assert _guarded_client().post("/launch", headers=headers).status_code == status
