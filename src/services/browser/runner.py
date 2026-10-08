import asyncio
import contextlib
import os
import signal
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

from camoufox.async_api import AsyncCamoufox

from src.core.config import DATA_DIR, HEADLESS, RESTORE_TABS
from src.services.browser import control, session
from src.services.browser.fingerprint import load_or_create
from src.services.proxy.geo_check import requests_proxy_url
from src.utils.proxy_parser import parse_proxy

_shutdown = asyncio.Event()

# How often the open tabs are snapshotted. The browser is stopped by killing
# this process, so whatever was saved last is what the next launch reopens.
TAB_SNAPSHOT_SECONDS = 2.0


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _safe_print(message: str) -> None:
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        fallback = (message + "\n").encode("utf-8", errors="replace")
        sys.stdout.buffer.write(fallback)
        sys.stdout.flush()


def _compact_error(exc: Exception, limit: int = 700) -> str:
    text = " ".join(str(exc).split())
    if "Call log:" in text:
        text = text.split("Call log:", 1)[0].strip()
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def _setup_signals(loop: asyncio.AbstractEventLoop) -> None:
    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _shutdown.set)
    except NotImplementedError:
        pass


def _open_urls(context: object) -> list[str]:
    return [p.url for p in context.pages if not p.is_closed()]


async def restore_tabs(context: object, urls: list[str]) -> int:
    """Reopen saved tabs: the first in the existing blank tab, the rest in new ones.

    Waits only for navigation to commit, so a slow site does not hold up the
    launch; a tab that fails to load stays open on whatever it reached.
    """
    if not urls:
        return 0
    first = context.pages[0] if context.pages else await context.new_page()
    pages = [first] + [await context.new_page() for _ in urls[1:]]

    async def go(page: object, url: str) -> None:
        try:
            await page.goto(url, wait_until="commit", timeout=15_000)
        except Exception as e:
            _safe_print(f"Could not restore tab {url}: {_compact_error(e, 120)}")

    await asyncio.gather(*(go(p, u) for p, u in zip(pages, urls, strict=True)))
    await pages[0].bring_to_front()
    return len(urls)


async def snapshot_tabs(context: object, profile_dir: str, stop: asyncio.Event) -> None:
    """Save the open tabs whenever they change, until `stop` is set."""
    last: list[str] = []
    while not stop.is_set():
        # asyncio.TimeoutError, not the builtin: they only became one in 3.11.
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=TAB_SNAPSHOT_SECONDS)
        if stop.is_set():
            # The last tab closing ends the session; keep the previous snapshot
            # instead of saving the now-empty window.
            return
        urls = session.restorable(_open_urls(context))
        if urls and urls != last and session.save(profile_dir, urls):
            last = urls


def geo_overrides(timezone: str, locale: str) -> dict:
    """Launch options that pin the timezone / locale instead of following the IP.

    Camoufox's geoip only fills in the timezone and locale when they are unset
    (setdefault for the config key, and `locale=` is applied after geoip), so the
    pinned values win while geolocation and the WebRTC IP still follow the proxy.
    """
    options: dict = {}
    if timezone:
        options["config"] = {"timezone": timezone}
    if locale:
        options["locale"] = locale
    return options


def exit_ip(proxy_str: str) -> str:
    """The exit IP Camoufox's geoip should use, looked up with DNS through the proxy.

    With `geoip=True` Camoufox looks it up itself over plain socks5://, which
    resolves the lookup hosts with the machine's own resolver at every launch.
    """
    from camoufox.ip import public_ip

    return public_ip(requests_proxy_url(proxy_str))


async def run_browser(
    profile_name: str,
    proxy_str: str,
    os_type: str,
    timezone: str = "",
    locale: str = "",
) -> int:
    profile_dir = os.path.join(os.getcwd(), DATA_DIR, profile_name)

    launch_config = {
        "headless": HEADLESS,
        "os": os_type,
        "fingerprint": load_or_create(profile_dir, os_type),
        "humanize": True,
        "geoip": exit_ip(proxy_str),
        "block_images": False,
        "user_data_dir": profile_dir,
        "persistent_context": True,
        **geo_overrides(timezone, locale),
    }

    proxy_config = parse_proxy(proxy_str)
    if proxy_config:
        launch_config["proxy"] = proxy_config

    _safe_print(f"Starting browser for {profile_name}...")

    try:
        async with AsyncCamoufox(**launch_config) as context:
            if not context.pages:
                await context.new_page()
            if RESTORE_TABS:
                restored = await restore_tabs(context, session.load(profile_dir))
                if restored:
                    _safe_print(f"Restored {restored} tab(s)")

            close_event = asyncio.Event()

            def on_page_close(_page: object) -> None:
                # The session ends when the last tab closes, not the first one.
                if not [p for p in context.pages if not p.is_closed()]:
                    close_event.set()

            def watch(page: object) -> None:
                page.on("close", on_page_close)

            for page in context.pages:
                watch(page)
            context.on("page", watch)
            context.on("close", lambda: close_event.set())

            control_runner, port, token = await control.serve(context)
            # CONTROL must precede BROWSER_STARTED: the launcher reports the
            # profile ready on BROWSER_STARTED and callers may control it at once.
            _safe_print(f"CONTROL:{port}:{token}")
            _safe_print("BROWSER_STARTED")

            snapshot_task = (
                asyncio.create_task(snapshot_tabs(context, profile_dir, close_event))
                if RESTORE_TABS
                else None
            )
            close_task = asyncio.create_task(close_event.wait())
            shutdown_task = asyncio.create_task(_shutdown.wait())

            done, pending = await asyncio.wait(
                [close_task, shutdown_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            if close_task in done:
                _safe_print("BROWSER_CLOSED")
            elif RESTORE_TABS:
                # Graceful shutdown (signal): the tabs are still open, save them.
                session.save(profile_dir, _open_urls(context))
            if snapshot_task:
                snapshot_task.cancel()
            await control_runner.cleanup()

            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

            return 0

    except asyncio.CancelledError:
        _safe_print("LAUNCH_CANCELLED")
        return 1
    except Exception as e:
        _safe_print(f"LAUNCH_FAILED: {type(e).__name__}: {_compact_error(e, 220)}")
        return 1


async def _async_main() -> int:
    loop = asyncio.get_running_loop()
    _setup_signals(loop)
    return await run_browser(*sys.argv[1:6])


if __name__ == "__main__":
    _configure_stdio()

    if len(sys.argv) < 4:
        _safe_print("Usage: python runner.py <name> <proxy> <os> [timezone] [locale]")
        sys.exit(1)

    exit_code = 1
    try:
        exit_code = asyncio.run(_async_main())
    except KeyboardInterrupt:
        _safe_print("Interrupted by user")
        exit_code = 130

    sys.exit(exit_code)
