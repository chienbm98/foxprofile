from __future__ import annotations

import contextlib
import pathlib
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse

from ..core.config import API_PORT, API_TOKEN, HEADLESS
from ..core.logging import get_logger
from . import mcp_http
from .auth import require_token
from .guard import LocalOnlyGuard
from .routes import (
    browser_router,
    mcp_setup_router,
    page_router,
    profiles_router,
    proxy_router,
)
from .schemas.common import SuccessResponse

if TYPE_CHECKING:
    from ..core.container import Container

logger = get_logger("api")

API_PREFIX = "/api/v1"
VERSION = "2.1.0"
_PANEL = pathlib.Path(__file__).resolve().parents[1] / "web" / "index.html"


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
        async with mcp_lifespan:
            yield

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
    app.include_router(mcp_setup_router, prefix=API_PREFIX, dependencies=protected)
    app.router.routes.append(mcp_route)

    @app.get(f"{API_PREFIX}/health", response_model=SuccessResponse, tags=["health"])
    def health_check() -> SuccessResponse:
        return SuccessResponse(message="FoxProfile API is running")

    @app.get(f"{API_PREFIX}/info", tags=["health"])
    def info() -> dict:
        """Public, secret-free facts the web panel needs before logging in."""
        return {
            "name": "FoxProfile",
            "version": VERSION,
            "auth_required": bool(API_TOKEN),
            "headless": HEADLESS,
            "mcp_path": mcp_http.MCP_PATH,
        }

    @app.get("/", include_in_schema=False)
    def panel() -> FileResponse:
        return FileResponse(_PANEL, headers={"Cache-Control": "no-store"})

    logger.info("FastAPI application created")
    return app
