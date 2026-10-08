"""Serve the MCP server over Streamable HTTP at /mcp, next to the REST API.

Remote MCP clients (Claude Code, Cursor, VS Code...) connect with a URL and the
same bearer token as the API, so FoxProfile on a VPS needs no local install.
The tools call back into this process's REST API over loopback.
"""

from __future__ import annotations

import contextlib
import secrets
from collections.abc import AsyncIterator

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from ..mcp_server import server as mcp_server

MCP_PATH = "/mcp"


def _bearer(scope: Scope) -> str:
    for key, value in scope["headers"]:
        if key == b"authorization":
            text = value.decode("latin-1")
            if text.lower().startswith("bearer "):
                return text[7:].strip()
        if key == b"x-api-key":
            return value.decode("latin-1").strip()
    return ""


def build(self_url: str, token: str) -> tuple[Route, contextlib.AbstractAsyncContextManager]:
    """Return the /mcp route and the lifespan context that runs its sessions."""
    mcp_server.configure(self_url, token)
    manager = StreamableHTTPSessionManager(
        app=mcp_server.mcp._mcp_server,
        stateless=True,
        json_response=True,
        # Host/Origin checks are done by LocalOnlyGuard (token-less) or the token.
        security_settings=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    class Endpoint:
        # A class instance, not a function: Starlette then passes raw ASGI
        # (scope, receive, send) instead of wrapping it as a Request handler.
        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if token and not secrets.compare_digest(_bearer(scope), token):
                response = JSONResponse(
                    {"detail": "Missing or invalid API token"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return
            await manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan() -> AsyncIterator[None]:
        async with manager.run():
            yield

    route = Route(MCP_PATH, endpoint=Endpoint(), methods=["GET", "POST", "DELETE"])
    return route, lifespan()
