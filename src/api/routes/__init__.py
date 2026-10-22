from .accounts import router as accounts_router
from .automation import router as automation_router
from .browser import router as browser_router
from .mcp_setup import router as mcp_setup_router
from .page import router as page_router
from .profiles import router as profiles_router
from .proxy import router as proxy_router
from .sync import router as sync_router
from .transfer import router as transfer_router

__all__ = [
    "accounts_router",
    "automation_router",
    "browser_router",
    "mcp_setup_router",
    "page_router",
    "profiles_router",
    "proxy_router",
    "sync_router",
    "transfer_router",
]
