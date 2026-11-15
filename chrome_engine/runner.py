"""FoxProfile runner for the Chrome engine.

Same command line and stdout protocol as src/services/browser/runner.py, so
BrowserLauncher can start a Chrome profile exactly like a Camoufox one:

    python -m chrome_engine.runner <name> <proxy> <os> [timezone] [locale]

prints CONTROL:<port>:<token>, then BROWSER_STARTED, and BROWSER_CLOSED when
the last tab closes (or LAUNCH_FAILED: ...). The page-control server, tab
restore and tab snapshots are FoxProfile's own, shared with Camoufox.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chrome_engine import fetch
from chrome_engine.engine import ChromeEngine
from src.core.config import HEADLESS, RESTORE_TABS, profile_data_dir
from src.services.browser import control, extensions, proton_login, session
from src.services.browser.runner import restore_tabs, snapshot_tabs

_shutdown = asyncio.Event()


def _say(message: str) -> None:
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((message + "\n").encode("utf-8", errors="replace"))
        sys.stdout.flush()


def _compact(exc: BaseException, limit: int = 220) -> str:
    text = " ".join(str(exc).split())
    text = text.split("Call log:", 1)[0].strip()
    return text[:limit] + ("..." if len(text) > limit else "")


def _install_progress() -> fetch.Progress:
    """Report download progress every 10% (the launcher shows these lines in the log)."""
    last = -1

    def report(done: int, total: int) -> None:
        nonlocal last
        pct = done * 100 // total if total else 0
        if pct // 10 != last // 10:
            last = pct
            _say(f"Downloading Chrome engine: {pct}% ({done / 1e6:.0f}/{total / 1e6:.0f} MB)")

    return report


async def ensure_installed() -> None:
    """Download the pinned browser build on first use."""
    if fetch.installed_executable():
        return
    _say("Chrome engine is not installed yet; downloading it once...")
    await asyncio.to_thread(fetch.install, progress=_install_progress())
    _say("Chrome engine installed")


def _headless() -> bool:
    # "virtual" means a hidden Xvfb display for Camoufox; Chrome runs headless instead.
    return HEADLESS in (True, "virtual")


async def run_browser(
    profile_name: str,
    proxy_str: str,
    os_type: str,
    timezone: str = "",
    locale: str = "",
    extension: str = "",
    country: str = "",
) -> int:
    profile_dir = profile_data_dir(profile_name)
    proxy = proxy_str if proxy_str and proxy_str != "None" else None

    # fingerprint-chromium is unbranded and still honours --load-extension.
    extra_args: list[str] = []
    if extension:
        _say("Preparing browser extensions...")
        try:
            extra_args = await asyncio.to_thread(extensions.chromium_extra_args, (extension,))
            if extension in extensions.EXTENSIONS:
                _say(f"Extension: {extensions.EXTENSIONS[extension].label}")
        except Exception as e:
            _say(f"Warning: browser extensions were not installed: {_compact(e, 200)}")

    engine = ChromeEngine(
        profile_dir,
        platform=os_type,
        proxy=proxy,
        headless=_headless(),
        # "" keeps the timezone / locale following the proxy's exit IP.
        timezone=timezone,
        locale=locale,
        extra_args=extra_args,
    )
    _say(f"Starting Chrome engine for {profile_name}...")
    try:
        await ensure_installed()
        context = await engine.start()
    except asyncio.CancelledError:
        _say("LAUNCH_CANCELLED")
        await engine.stop()
        return 1
    except Exception as e:
        _say(f"LAUNCH_FAILED: {type(e).__name__}: {_compact(e)}")
        await engine.stop()
        return 1

    try:
        for warning in engine.warnings:
            _say(f"Warning: {warning}")
        if not context.pages:
            await context.new_page()

        close_event = asyncio.Event()

        def on_page_close(_page: object) -> None:
            if not [p for p in context.pages if not p.is_closed()]:
                close_event.set()

        def watch(page: object) -> None:
            page.on("close", on_page_close)

        for page in context.pages:
            watch(page)
        context.on("page", watch)
        context.on("close", lambda _: close_event.set())

        proton = extension == "proton-vpn"
        if proton:
            if not proton_login.configured(profile_name):
                _say("LAUNCH_FAILED: no Proton account saved for this profile")
                return 1
            try:
                signed_in = await asyncio.wait_for(
                    proton_login.auto_login(
                        context,
                        profile_dir,
                        "chrome",
                        profile_name,
                        keep_open=not _headless(),
                        log=_say,
                        country=country,
                    ),
                    timeout=100,
                )
            except asyncio.TimeoutError:
                _say("LAUNCH_FAILED: Proton VPN sign-in timed out")
                return 1
            if not signed_in:
                _say("LAUNCH_FAILED: Proton VPN sign-in failed")
                return 1
            try:
                connected = await asyncio.wait_for(
                    proton_login.ensure_connected(context, country, _say), timeout=70
                )
            except asyncio.TimeoutError:
                _say("LAUNCH_FAILED: Proton VPN connection timed out")
                return 1
            except Exception as e:
                _say(f"LAUNCH_FAILED: Proton VPN connection failed: {_compact(e)}")
                return 1
            if not connected:
                _say("LAUNCH_FAILED: Proton VPN did not connect")
                return 1
            # Keep one blank tab and drop the tabs used for the sign-in, so
            # they never end up in tabs.json and no old tab loads before the VPN.
            blank = await context.new_page()
            for page in list(context.pages):
                if page is blank:
                    continue
                with contextlib.suppress(Exception):
                    if page.url.startswith(("https://account.proton.me", "chrome-extension://")):
                        await page.close()

        if RESTORE_TABS:
            restored = await restore_tabs(context, session.load(profile_dir))
            if restored:
                _say(f"Restored {restored} tab(s)")

        control_runner, port, token = await control.serve(context)
        # CONTROL must precede BROWSER_STARTED (see the Camoufox runner).
        _say(f"CONTROL:{port}:{token}")
        _say("BROWSER_STARTED")

        snapshot_task = (
            asyncio.create_task(snapshot_tabs(context, profile_dir, close_event))
            if RESTORE_TABS
            else None
        )
        close_task = asyncio.create_task(close_event.wait())
        shutdown_task = asyncio.create_task(_shutdown.wait())
        done, pending = await asyncio.wait(
            [close_task, shutdown_task], return_when=asyncio.FIRST_COMPLETED
        )
        if close_task in done:
            _say("BROWSER_CLOSED")
        elif RESTORE_TABS:
            session.save(profile_dir, [p.url for p in context.pages if not p.is_closed()])
        if snapshot_task:
            snapshot_task.cancel()
        await control_runner.cleanup()
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        return 0
    finally:
        await engine.stop()


async def _async_main(argv: list[str]) -> int:
    loop = asyncio.get_running_loop()
    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _shutdown.set)
    except NotImplementedError:
        pass
    return await run_browser(*argv[:7])


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 4:
        _say(
            "Usage: python -m chrome_engine.runner "
            "<name> <proxy> <os> [timezone] [locale] [extension] [country]"
        )
        return 1
    try:
        return asyncio.run(_async_main(sys.argv[1:]))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
