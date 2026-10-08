"""Ready-to-paste MCP client configurations, shared by the desktop app and the web panel."""

from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import asdict, dataclass

TOKEN_PLACEHOLDER = "<FOXPROFILE_API_TOKEN>"
MCP_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "foxprofile_mcp.py"


@dataclass
class ClientConfig:
    id: str
    name: str
    where: str  # where the snippet goes: a terminal or a config file path
    language: str  # "bash" or "json", for display
    code: str


def _json(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def build_configs(
    mcp_url: str,
    token: str | None,
    *,
    local: bool,
    python: str | None = None,
    api_url: str | None = None,
) -> list[ClientConfig]:
    """Configs for common MCP clients.

    `token` is the real token, a placeholder, or None when the API has none.
    `local` adds a Claude Desktop config that starts FoxProfile's stdio MCP
    server on this machine; otherwise Claude Desktop goes through mcp-remote.
    """
    auth = {"Authorization": f"Bearer {token}"} if token else {}
    header_flag = f' --header "Authorization: Bearer {token}"' if token else ""

    configs = [
        ClientConfig(
            id="claude-code",
            name="Claude Code",
            where="Terminal",
            language="bash",
            code=f"claude mcp add --transport http foxprofile {mcp_url}{header_flag}",
        ),
        ClientConfig(
            id="cursor",
            name="Cursor",
            where="~/.cursor/mcp.json",
            language="json",
            code=_json(
                {
                    "mcpServers": {
                        "foxprofile": {"url": mcp_url, **({"headers": auth} if auth else {})}
                    }
                },
            ),
        ),
        ClientConfig(
            id="vscode",
            name="VS Code",
            where=".vscode/mcp.json",
            language="json",
            code=_json(
                {
                    "servers": {
                        "foxprofile": {
                            "type": "http",
                            "url": mcp_url,
                            **({"headers": auth} if auth else {}),
                        },
                    },
                },
            ),
        ),
    ]

    desktop_where = (
        "%APPDATA%\\Claude\\claude_desktop_config.json"
        if sys.platform == "win32"
        else "~/Library/Application Support/Claude/claude_desktop_config.json"
    )
    if local:
        env = {"FOXPROFILE_URL": api_url or mcp_url.rsplit("/mcp", 1)[0]}
        if token:
            env["FOXPROFILE_API_TOKEN"] = token
        server = {
            "command": python or sys.executable,
            "args": [str(MCP_SCRIPT)],
            "env": env,
        }
    else:
        # Claude Desktop's config file only starts local (stdio) servers;
        # mcp-remote bridges it to the HTTP endpoint.
        args = ["-y", "mcp-remote", mcp_url]
        server = {"command": "npx", "args": args}
        if token:
            args += ["--header", "Authorization:${FOXPROFILE_AUTH}"]
            server["env"] = {"FOXPROFILE_AUTH": f"Bearer {token}"}
    configs.append(
        ClientConfig(
            id="claude-desktop",
            name="Claude Desktop",
            where=desktop_where,
            language="json",
            code=_json({"mcpServers": {"foxprofile": server}}),
        ),
    )
    return configs


def as_dicts(configs: list[ClientConfig]) -> list[dict]:
    return [asdict(c) for c in configs]
