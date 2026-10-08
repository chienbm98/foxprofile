import asyncio
import os
import signal
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

from camoufox.async_api import AsyncCamoufox

from src.core.config import DATA_DIR, HEADLESS
from src.services.browser import control
from src.services.browser.fingerprint import load_or_create
from src.utils.proxy_parser import parse_proxy

_shutdown = asyncio.Event()


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
        "geoip": True,
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

            close_task = asyncio.create_task(close_event.wait())
            shutdown_task = asyncio.create_task(_shutdown.wait())

            done, pending = await asyncio.wait(
                [close_task, shutdown_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            if close_task in done:
                _safe_print("BROWSER_CLOSED")
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
