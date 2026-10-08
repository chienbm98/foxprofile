from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query

from ...core.config import API_TOKEN
from ...services import mcp_setup
from ..mcp_http import MCP_PATH

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.get("/setup")
def setup(
    base_url: str = Query(description="Address the client uses to reach FoxProfile"),
) -> dict:
    """MCP client configs for this server. The token appears as a placeholder."""
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail="base_url must be an http(s) URL")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    mcp_url = origin + MCP_PATH
    token = mcp_setup.TOKEN_PLACEHOLDER if API_TOKEN else None
    return {
        "mcp_url": mcp_url,
        "auth_required": bool(API_TOKEN),
        "token_placeholder": mcp_setup.TOKEN_PLACEHOLDER,
        "configs": mcp_setup.as_dicts(mcp_setup.build_configs(mcp_url, token, local=False)),
    }
