"""Protect the token-less local API from websites open in the user's own browser.

Without a token, two attacks work from any page the user visits:
- CSRF: a simple cross-origin POST (no preflight) launches or stops profiles.
- DNS rebinding: a domain re-resolved to 127.0.0.1 can read responses, so it
  could export cookies or run JavaScript inside a profile.

The middleware rejects requests whose Host is not a loopback name (defeats
rebinding) and requests whose Origin is not a loopback origin (defeats CSRF).
With a token configured neither attack applies: browsers cannot attach the
Authorization header cross-origin without a CORS grant, which the API never gives.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_LOOPBACK_NAMES = {"127.0.0.1", "localhost", "::1", "[::1]"}
_HOST_PORT = re.compile(r"^(\[[^\]]+\]|[^:]+)(?::\d+)?$")


def _host_name(host: str) -> str:
    match = _HOST_PORT.match(host.strip().lower())
    return match.group(1) if match else ""


def is_loopback_host_header(host: str) -> bool:
    return _host_name(host) in _LOOPBACK_NAMES


def is_loopback_origin(origin: str) -> bool:
    parsed = urlparse(origin.strip().lower())
    return parsed.scheme in ("http", "https") and (parsed.hostname or "") in {
        "127.0.0.1",
        "localhost",
        "::1",
    }


class LocalOnlyGuard:
    """ASGI middleware; install it only when the API runs without a token."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}
        origin = headers.get("origin")
        reason = None
        if not is_loopback_host_header(headers.get("host", "")):
            reason = "Host header is not a loopback address"
        elif origin is not None and not is_loopback_origin(origin):
            # Includes Origin: null (sandboxed iframes, file:// pages).
            reason = "Cross-origin requests are not allowed"
        if reason:
            await JSONResponse({"detail": reason}, status_code=403)(scope, receive, send)
            return
        await self.app(scope, receive, send)
