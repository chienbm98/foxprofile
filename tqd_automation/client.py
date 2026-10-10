"""Drive one profile's browser through the FoxProfile REST API.

Reuses the MCP server's REST helpers instead of a second HTTP client. The API URL and token come
from `FOXPROFILE_URL` / `FOXPROFILE_API_TOKEN`, read from `.env` when present.
"""

from __future__ import annotations

import base64
import os
import time
from typing import Any

from dotenv import load_dotenv

from src.mcp_server import server
from src.mcp_server.server import FoxProfileError, _page, _quote

load_dotenv()
server.configure(
    os.getenv("FOXPROFILE_URL", "http://127.0.0.1:8000"), os.getenv("FOXPROFILE_API_TOKEN", "")
)

READY_TIMEOUT = 90
POLL_SECONDS = 2


class Browser:
    def __init__(self, profile: str):
        self.profile = profile

    def _act(self, method: str, suffix: str, body: dict | None = None, **query: Any) -> Any:
        return server._request(method, _page(self.profile, suffix), body, query or None)

    def ensure_running(self, timeout: float = READY_TIMEOUT) -> None:
        """Launch the profile if needed and wait until its pages can be controlled."""
        name = _quote(self.profile)
        if not server._request("GET", f"/browser/{name}/status")["is_running"]:
            try:
                # Blocks until ready, or answers 202 while the browser is still starting.
                server._request("POST", f"/browser/{name}/launch")
            except FoxProfileError as e:
                if "Browser already running" not in str(e):  # a concurrent launch won the race
                    raise
        deadline = time.monotonic() + timeout
        while True:
            try:
                self._act("GET", "tabs")
                return
            except FoxProfileError as e:
                if time.monotonic() >= deadline:
                    raise FoxProfileError(
                        f"Browser for '{self.profile}' was not ready after {timeout:.0f}s: {e}"
                    ) from e
            time.sleep(POLL_SECONDS)

    def navigate(self, url: str) -> dict:
        return self._act("POST", "navigate", {"url": url})

    def snapshot(self, interactive_only: bool = False) -> dict:
        return self._act("GET", "snapshot", interactive_only=str(interactive_only).lower())

    def click(self, selector: str, timeout: int = 10_000) -> dict:
        return self._act("POST", "click", {"selector": selector, "timeout": timeout})

    def keyboard_type(self, text: str) -> dict:
        return self._act("POST", "keyboard", {"text": text})

    def upload(self, selector: str, paths: list[str]) -> dict:
        return self._act("POST", "upload", {"selector": selector, "paths": paths})

    def wait_for_url(self, pattern: str, timeout: int = 15_000) -> dict:
        return self._act("POST", "wait-url", {"pattern": pattern, "timeout": timeout})

    def wait_for_text(self, text: str, timeout: int = 15_000) -> dict:
        return self._act("POST", "wait-text", {"text": text, "timeout": timeout})

    def wait_for(self, selector: str, timeout: int = 15_000) -> dict:
        return self._act("POST", "wait", {"selector": selector, "timeout": timeout})

    def scroll(self, dy: int = 600, to: str | None = None) -> dict:
        return self._act("POST", "scroll", {"dy": dy, "to": to})

    def screenshot_png(self) -> bytes:
        return base64.b64decode(self._act("GET", "screenshot", format="json")["png_base64"])

    def evaluate(self, script: str) -> Any:
        return self._act("POST", "evaluate", {"script": script})
