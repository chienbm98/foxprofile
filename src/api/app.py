from __future__ import annotations

import contextlib
import hashlib
import os
import pathlib
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from ..core.config import API_PORT, API_TOKEN, HEADLESS
from ..core.logging import get_logger
from . import mcp_http
from .auth import require_token
from .guard import LocalOnlyGuard
from .routes import (
    accounts_router,
    automation_router,
    browser_router,
    mcp_setup_router,
    page_router,
    profiles_router,
    proxy_router,
    sync_router,
    transfer_router,
)
from .schemas.common import SuccessResponse

if TYPE_CHECKING:
    from ..core.container import Container

logger = get_logger("api")

API_PREFIX = "/api/v1"


def instance_id(data_dir: str) -> str:
    """sha1 of the data folder path, lower case with backslashes and no trailing slash. The
    start script computes the same value, so both sides agree whatever the path's spelling."""
    norm = data_dir.replace("/", "\\").rstrip("\\").lower()
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()


VERSION = "2.3.1"
_PANEL = pathlib.Path(__file__).resolve().parents[1] / "web" / "index.html"
_FONTS = pathlib.Path(__file__).resolve().parents[1] / "assets" / "fonts"
# Served to the panel without a token: it needs them before login.
_FONT_FILES = {f.name: f for f in _FONTS.glob("*.ttf")}


def create_app(container: Container, self_url: str | None = None) -> FastAPI:
    """Build the FastAPI application.

    `self_url` is where this process's own API is reachable over loopback; the
    MCP endpoint's tools call back into it.
    """
    mcp_route, mcp_lifespan = mcp_http.build(
        self_url or f"http://127.0.0.1:{API_PORT}",
        API_TOKEN,
    )

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        automation = container.automation
        automation.start()
        try:
            async with mcp_lifespan:
                yield
        finally:
            automation.shutdown()

    app = FastAPI(
        lifespan=lifespan,
        title="FoxProfile API",
        description=(
            "REST API for FoxProfile (Camoufox profile manager). When "
            "FOXPROFILE_API_TOKEN is set, send it as `Authorization: Bearer <token>`."
        ),
        version=VERSION,
    )
    app.state.container = container
    if not API_TOKEN:
        # Token-less means local-only: block CSRF and DNS rebinding from websites.
        app.add_middleware(LocalOnlyGuard)

    protected = [Depends(require_token)]
    app.include_router(profiles_router, prefix=API_PREFIX, dependencies=protected)
    app.include_router(browser_router, prefix=API_PREFIX, dependencies=protected)
    app.include_router(page_router, prefix=API_PREFIX, dependencies=protected)
    app.include_router(proxy_router, prefix=API_PREFIX, dependencies=protected)
    app.include_router(accounts_router, prefix=API_PREFIX, dependencies=protected)
    app.include_router(sync_router, prefix=API_PREFIX, dependencies=protected)
    app.include_router(transfer_router, prefix=API_PREFIX, dependencies=protected)
    app.include_router(automation_router, prefix=API_PREFIX, dependencies=protected)
    app.include_router(mcp_setup_router, prefix=API_PREFIX, dependencies=protected)
    app.router.routes.append(mcp_route)

    @app.get(f"{API_PREFIX}/health", response_model=SuccessResponse, tags=["health"])
    def health_check() -> SuccessResponse:
        return SuccessResponse(message="FoxProfile API is running")

    @app.get(f"{API_PREFIX}/info", tags=["health"])
    def info(request: Request) -> dict:
        """Public, secret-free facts the web panel needs before logging in."""
        data_dir = os.getcwd()
        result = {
            "name": "FoxProfile",
            "version": VERSION,
            "auth_required": bool(API_TOKEN),
            "headless": HEADLESS,
            "mcp_path": mcp_http.MCP_PATH,
            # Identifies which data folder this server serves, so a launcher can tell its own
            # server from another FoxProfile copy that already holds the port.
            "instance": instance_id(data_dir),
        }
        if (request.client.host if request.client else "") in ("127.0.0.1", "::1", "localhost"):
            result["data_dir"] = data_dir
        return result

    @app.get("/", include_in_schema=False)
    def panel() -> FileResponse:
        return FileResponse(_PANEL, headers={"Cache-Control": "no-store"})

    @app.get("/assets/fonts/{name}", include_in_schema=False)
    def font(name: str) -> FileResponse:
        path = _FONT_FILES.get(name)
        if path is None:
            raise HTTPException(status_code=404)
        return FileResponse(
            path, media_type="font/ttf", headers={"Cache-Control": "public, max-age=604800"}
        )

    logger.info("FastAPI application created")
    return app
