import json

from fastapi.testclient import TestClient

from src.api import mcp_http
from src.services import mcp_setup

URL = "https://vps.example.com/mcp"


def _by_id(configs):
    return {c.id: c for c in configs}


def test_configs_without_token_have_no_auth():
    configs = _by_id(mcp_setup.build_configs(URL, None, local=False))
    assert set(configs) == {"claude-code", "cursor", "vscode", "claude-desktop"}
    assert configs["claude-code"].code == f"claude mcp add --transport http foxprofile {URL}"
    assert "headers" not in json.loads(configs["cursor"].code)["mcpServers"]["foxprofile"]
    assert "Authorization" not in configs["claude-desktop"].code


def test_configs_with_token_are_valid_json_and_carry_header():
    configs = _by_id(mcp_setup.build_configs(URL, "tok", local=False))
    assert '--header "Authorization: Bearer tok"' in configs["claude-code"].code
    cursor = json.loads(configs["cursor"].code)["mcpServers"]["foxprofile"]
    assert cursor == {"url": URL, "headers": {"Authorization": "Bearer tok"}}
    vscode = json.loads(configs["vscode"].code)["servers"]["foxprofile"]
    assert vscode["type"] == "http" and vscode["headers"]["Authorization"] == "Bearer tok"
    desktop = json.loads(configs["claude-desktop"].code)["mcpServers"]["foxprofile"]
    assert desktop["command"] == "npx" and URL in desktop["args"]
    assert desktop["env"]["FOXPROFILE_AUTH"] == "Bearer tok"


def test_local_desktop_config_uses_stdio_bridge():
    configs = _by_id(
        mcp_setup.build_configs(
            "http://127.0.0.1:8000/mcp",
            None,
            local=True,
            python="py",
            api_url="http://127.0.0.1:8000",
        ),
    )
    desktop = json.loads(configs["claude-desktop"].code)["mcpServers"]["foxprofile"]
    assert desktop["command"] == "py"
    assert desktop["args"] == [str(mcp_setup.MCP_SCRIPT)]
    assert desktop["env"] == {"FOXPROFILE_URL": "http://127.0.0.1:8000"}
    assert mcp_setup.MCP_SCRIPT.exists()


def _mcp_client(token):
    from starlette.applications import Starlette

    route, lifespan = mcp_http.build("http://127.0.0.1:1", token)

    async def _lifespan(_app):
        async with lifespan:
            yield

    from contextlib import asynccontextmanager

    return TestClient(Starlette(routes=[route], lifespan=asynccontextmanager(_lifespan)))


_INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "t", "version": "1"},
    },
}
_HEADERS = {"Accept": "application/json, text/event-stream"}


def test_mcp_endpoint_requires_token():
    with _mcp_client("x" * 32) as client:
        assert client.post("/mcp", json=_INIT, headers=_HEADERS).status_code == 401
        ok = client.post(
            "/mcp",
            json=_INIT,
            headers={**_HEADERS, "Authorization": "Bearer " + "x" * 32},
        )
        assert ok.status_code == 200
        assert ok.json()["result"]["serverInfo"]["name"] == "foxprofile"
