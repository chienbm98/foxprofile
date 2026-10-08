from .browser import router as browser_router
from .page import router as page_router
from .profiles import router as profiles_router
from .proxy import router as proxy_router

__all__ = ["browser_router", "page_router", "profiles_router", "proxy_router"]
