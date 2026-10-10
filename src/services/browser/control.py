"""Remote control of a running profile's pages.

runner.py starts `serve()` next to the browser. It listens on 127.0.0.1 on a
random port, requires a random per-launch token, and announces itself on
stdout as "CONTROL:<port>:<token>" so the launcher can forward API calls.
"""

from __future__ import annotations

import base64
import os
import pathlib
import re
import secrets
from typing import Any
from urllib.parse import unquote, urlparse

from aiohttp import web

from ...core.config import UPLOAD_DIR

ALLOWED_SCHEMES = ("http", "https", "about")
MAX_FULL_PAGE_HEIGHT = 16_384
MAX_TEXT = 40_000
TOKEN_HEADER = "X-Control-Token"
ALLOWED_UPLOAD_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".webm"}
MAX_UPLOAD_BYTES = 512 * 1024 * 1024
# Roles an agent can act on; `snapshot(interactive_only=True)` keeps only these lines.
_INTERACTIVE = re.compile(
    r"^\s*- (button|link|textbox|searchbox|combobox|checkbox|radio|switch|tab|menuitem|option|slider)\b",
)


class ControlError(Exception):
    pass


_SCHEME = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):(.*)$", re.S)


def _check_url(url: str) -> str:
    url = url.strip()
    # "%66ile:" or "java%73cript:" would miss _SCHEME and get https:// prepended;
    # decode a percent-encoded scheme and check it like any other.
    colon = url.find(":")
    slash = url.find("/")
    if colon != -1 and "%" in url[:colon] and (slash == -1 or colon < slash):
        decoded_scheme = unquote(url[:colon]).lower()
        if decoded_scheme not in ALLOWED_SCHEMES:
            raise ControlError(f"URL scheme '{decoded_scheme}' is not allowed")

    match = _SCHEME.match(url)
    # "localhost:8080/x" looks like a scheme but is host:port; bare hosts get https.
    if not match or re.match(r"\d+(/|$)", match.group(2)):
        url = "https://" + url
    try:
        parsed = urlparse(url)
        host = parsed.hostname
    except ValueError as e:  # e.g. an unclosed IPv6 bracket: "[::1"
        raise ControlError(f"Malformed URL: {e}") from e
    scheme = parsed.scheme.lower()
    if scheme in ("http", "https") and not host:
        # Older Python versions parse "https://[]" without raising.
        raise ControlError("Malformed URL: no host")
    if scheme not in ALLOWED_SCHEMES:
        # file:, view-source:, chrome: etc. would let a remote caller read
        # local files or browser internals through the snapshot.
        raise ControlError(f"URL scheme '{scheme}' is not allowed")
    if scheme == "about" and url.lower() != "about:blank":
        # about:config, about:logins etc. expose or change browser internals.
        raise ControlError("Only about:blank is allowed among about: pages")
    return url


def _check_upload(paths: list[str]) -> list[str]:
    """Resolve upload paths, refusing anything outside the upload directory.

    A page can ask an agent to "attach" a file; confining uploads to one folder
    keeps cookies and other private files out of reach.
    """
    if not paths:
        raise ControlError("Give at least one file to upload")
    root = pathlib.Path(os.getcwd(), UPLOAD_DIR).resolve()
    resolved = []
    for raw in paths:
        path = pathlib.Path(os.getcwd(), raw).resolve()
        if not path.is_relative_to(root):
            raise ControlError(f"'{raw}' is outside the upload directory {UPLOAD_DIR}")
        if not path.is_file():
            raise ControlError(f"'{raw}' not found")
        if path.suffix.lower() not in ALLOWED_UPLOAD_EXT:
            raise ControlError(f"File type '{path.suffix}' is not allowed for upload")
        if path.stat().st_size > MAX_UPLOAD_BYTES:
            raise ControlError(f"'{raw}' is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
        resolved.append(str(path))
    return resolved


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True


class PageController:
    """Executes control actions against a Playwright BrowserContext."""

    def __init__(self, context: Any) -> None:
        self._context = context
        self._current: Any = None

    # --- page selection ---------------------------------------------------

    def _open_pages(self) -> list[Any]:
        return [p for p in self._context.pages if not p.is_closed()]

    async def _page(self) -> Any:
        pages = self._open_pages()
        if self._current is not None and not self._current.is_closed():
            return self._current
        if pages:
            self._current = pages[-1]
            return self._current
        self._current = await self._context.new_page()
        return self._current

    async def _describe(self, page: Any) -> dict[str, Any]:
        return {"url": page.url, "title": await page.title()}

    # --- actions ----------------------------------------------------------

    async def navigate(self, url: str, wait_until: str = "load") -> dict[str, Any]:
        page = await self._page()
        await page.goto(_check_url(url), wait_until=wait_until)
        return await self._describe(page)

    async def back(self) -> dict[str, Any]:
        page = await self._page()
        await page.go_back()
        return await self._describe(page)

    async def snapshot(
        self, max_chars: int = MAX_TEXT, interactive_only: bool = False
    ) -> dict[str, Any]:
        """Accessibility tree of the page: roles, names and text, compact.

        `interactive_only` keeps just the controls an agent can act on, which is
        usually a fraction of the tokens of the full tree.
        """
        page = await self._page()
        aria = await page.locator("body").aria_snapshot()
        if interactive_only:
            aria = "\n".join(line for line in aria.splitlines() if _INTERACTIVE.match(line))
        aria, truncated = _truncate(aria, max_chars)
        return {**await self._describe(page), "snapshot": aria, "truncated": truncated}

    async def text(self, selector: str = "body", max_chars: int = MAX_TEXT) -> dict[str, Any]:
        page = await self._page()
        content = await page.locator(selector).first.inner_text()
        content, truncated = _truncate(content, max_chars)
        return {"text": content, "truncated": truncated}

    async def click(self, selector: str, timeout: int = 10_000) -> dict[str, Any]:
        page = await self._page()
        await page.locator(selector).first.click(timeout=timeout)
        return await self._describe(page)

    async def type(
        self,
        selector: str,
        text: str,
        submit: bool = False,
        clear: bool = True,
        timeout: int = 10_000,
    ) -> dict[str, Any]:
        page = await self._page()
        field = page.locator(selector).first
        if clear:
            await field.fill(text, timeout=timeout)
        else:
            await field.press_sequentially(text, timeout=timeout)
        if submit:
            await field.press("Enter")
        return await self._describe(page)

    async def press(self, key: str, selector: str | None = None) -> dict[str, Any]:
        page = await self._page()
        if selector:
            await page.locator(selector).first.press(key)
        else:
            await page.keyboard.press(key)
        return await self._describe(page)

    async def click_at(self, x: float, y: float) -> dict[str, Any]:
        """Click viewport coordinates, as seen on a screenshot of the active tab."""
        page = await self._page()
        await page.mouse.click(x, y)
        return await self._describe(page)

    async def keyboard_type(self, text: str) -> dict[str, Any]:
        """Type into whatever element has focus."""
        page = await self._page()
        await page.keyboard.type(text)
        return await self._describe(page)

    async def wait_for(self, selector: str, timeout: int = 15_000) -> dict[str, Any]:
        page = await self._page()
        await page.locator(selector).first.wait_for(timeout=timeout)
        return await self._describe(page)

    async def wait_for_url(self, pattern: str, timeout: int = 15_000) -> dict[str, Any]:
        """Wait until the active tab's URL contains `pattern`."""
        page = await self._page()
        await page.wait_for_url(f"**{pattern}**", timeout=timeout)
        return await self._describe(page)

    async def wait_for_text(self, text: str, timeout: int = 15_000) -> dict[str, Any]:
        page = await self._page()
        await page.get_by_text(text).first.wait_for(timeout=timeout)
        return await self._describe(page)

    async def scroll(self, dy: int = 600, to: str | None = None) -> dict[str, Any]:
        """Scroll by `dy` pixels with the mouse wheel, or jump `to` the top or bottom."""
        page = await self._page()
        if to == "top":
            await page.evaluate("window.scrollTo(0, 0)")
        elif to == "bottom":
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        elif to is None:
            await page.mouse.wheel(0, dy)
        else:
            raise ControlError("Scroll 'to' must be 'top' or 'bottom'")
        return await self._describe(page)

    async def upload(
        self, selector: str, paths: list[str], timeout: int = 15_000
    ) -> dict[str, Any]:
        """Set files on a file input, hidden ones included; files must be in the upload directory."""
        files = _check_upload(paths)
        page = await self._page()
        await page.locator(selector).first.set_input_files(files, timeout=timeout)
        return {**await self._describe(page), "uploaded": len(files)}

    async def screenshot(self, full_page: bool = False) -> dict[str, Any]:
        page = await self._page()
        if full_page:
            height = await page.evaluate("() => document.documentElement.scrollHeight")
            if height > MAX_FULL_PAGE_HEIGHT:
                raise ControlError(
                    f"Page is {height}px tall; full-page screenshots are limited to "
                    f"{MAX_FULL_PAGE_HEIGHT}px. Scroll and take viewport screenshots instead.",
                )
        png = await page.screenshot(full_page=full_page, type="png")
        return {**await self._describe(page), "png_base64": base64.b64encode(png).decode()}

    async def evaluate(self, script: str) -> dict[str, Any]:
        page = await self._page()
        return {"result": await page.evaluate(script)}

    async def tabs(self) -> dict[str, Any]:
        current = await self._page()
        pages = self._open_pages()
        return {
            "tabs": [
                {"index": i, "url": p.url, "title": await p.title(), "active": p is current}
                for i, p in enumerate(pages)
            ],
        }

    async def tab_new(self, url: str | None = None) -> dict[str, Any]:
        self._current = await self._context.new_page()
        if url:
            await self._current.goto(_check_url(url))
        return await self.tabs()

    async def tab_select(self, index: int) -> dict[str, Any]:
        pages = self._open_pages()
        if not 0 <= index < len(pages):
            raise ControlError(f"No tab at index {index}")
        self._current = pages[index]
        await self._current.bring_to_front()
        return await self.tabs()

    async def tab_close(self, index: int) -> dict[str, Any]:
        pages = self._open_pages()
        if not 0 <= index < len(pages):
            raise ControlError(f"No tab at index {index}")
        if len(pages) == 1:
            # Closing the last tab closes the profile's browser.
            raise ControlError("Cannot close the last tab; stop the profile instead")
        await pages[index].close()
        self._current = None
        return await self.tabs()

    ACTIONS = (
        "navigate",
        "back",
        "snapshot",
        "text",
        "click",
        "type",
        "press",
        "click_at",
        "keyboard_type",
        "wait_for",
        "wait_for_url",
        "wait_for_text",
        "scroll",
        "upload",
        "screenshot",
        "evaluate",
        "tabs",
        "tab_new",
        "tab_select",
        "tab_close",
    )

    async def dispatch(self, action: str, params: dict[str, Any]) -> Any:
        if action not in self.ACTIONS:
            raise ControlError(f"Unknown action '{action}'")
        try:
            return await getattr(self, action)(**params)
        except TypeError as e:
            raise ControlError(f"Invalid parameters for '{action}': {e}") from e


def build_app(controller: PageController, token: str) -> web.Application:
    async def handle(request: web.Request) -> web.Response:
        if not secrets.compare_digest(request.headers.get(TOKEN_HEADER, ""), token):
            return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
        try:
            body = await request.json()
            result = await controller.dispatch(body.get("action", ""), body.get("params") or {})
        except ControlError as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)
        except Exception as e:  # Playwright timeouts, navigation errors, JS errors
            message = " ".join(str(e).split())
            if "Call log:" in message:
                message = message.split("Call log:", 1)[0].strip()
            return web.json_response(
                {"ok": False, "error": f"{type(e).__name__}: {message[:500]}"},
                status=422,
            )
        return web.json_response({"ok": True, "result": result})

    app = web.Application(client_max_size=4 * 1024 * 1024)
    app.router.add_post("/action", handle)
    return app


async def serve(context: Any) -> tuple[web.AppRunner, int, str]:
    """Start the control server for a context. Returns (runner, port, token)."""
    token = secrets.token_urlsafe(24)
    runner = web.AppRunner(build_app(PageController(context), token), access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, port, token
