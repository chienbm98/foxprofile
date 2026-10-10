import logging
import threading
from collections.abc import Callable

from ..interfaces.protocols import IBrowserLauncher, IProfileManager, IProxyService
from .config import LOG_DIR, LOG_LEVEL
from .events import EventBus
from .logging import setup_logging


class Container:
    def __init__(self) -> None:
        setup_logging(LOG_DIR, getattr(logging, LOG_LEVEL, logging.INFO))
        self._instances: dict = {}
        # The first API requests arrive on several worker threads at once; each
        # service must be built exactly once or they would hold separate state.
        self._lock = threading.RLock()

    def _get(self, key: str, build: Callable[[], object]):
        instance = self._instances.get(key)
        if instance is None:
            with self._lock:
                instance = self._instances.get(key)
                if instance is None:
                    instance = self._instances[key] = build()
        return instance

    @property
    def event_bus(self) -> EventBus:
        return self._get("eb", EventBus)

    @property
    def profile_manager(self) -> IProfileManager:
        from ..services.profile.manager import ProfileManager

        return self._get("pm", ProfileManager)

    @property
    def browser_launcher(self) -> IBrowserLauncher:
        from ..services.browser.launcher import BrowserLauncher

        return self._get("bl", BrowserLauncher)

    @property
    def proxy_service(self) -> IProxyService:
        from ..services.proxy.service import ProxyService

        return self._get("ps", ProxyService)
