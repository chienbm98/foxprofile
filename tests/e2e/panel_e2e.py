"""Drive the web panel in a real browser: login, launch, remote view, navigate, stop."""

import asyncio
import contextlib
import os
import pathlib

from camoufox.async_api import AsyncCamoufox

OUT_DIR = pathlib.Path(os.getenv("E2E_OUT", "e2e-output"))
OUT_DIR.mkdir(exist_ok=True)

URL = os.getenv("FOXPROFILE_URL", "http://127.0.0.1:8000").rstrip("/") + "/"
TOKEN = os.environ.get("FOXPROFILE_API_TOKEN", "")
OUT = str(OUT_DIR)
errors = []


def reset():
    import urllib.request

    for method, path in (
        ("POST", "/api/v1/browser/mcp-demo/stop"),
        ("DELETE", "/api/v1/profiles/panel-demo"),
    ):
        req = urllib.request.Request(
            os.getenv("FOXPROFILE_URL", "http://127.0.0.1:8000").rstrip("/") + path,
            method=method,
            headers={"Authorization": "Bearer " + TOKEN},
        )
        with contextlib.suppress(Exception):
            urllib.request.urlopen(req, timeout=30)


async def main():
    reset()
    async with AsyncCamoufox(headless=True, os="windows", window=(1400, 900)) as browser:
        page = await browser.new_page(viewport={"width": 1400, "height": 900})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: m.type == "error" and errors.append(f"console: {m.text}"))
        await page.goto(URL)

        await page.wait_for_selector("#login:not(.hidden)")
        await page.fill("#token", "wrong-token-wrong-token-wrong")
        await page.click("#login-form button")
        await page.wait_for_function("document.getElementById('login-err').textContent.length > 0")
        print("wrong token message:", await page.text_content("#login-err"))
        await page.screenshot(path=OUT + r"\panel_login.png")

        await page.fill("#token", TOKEN)
        await page.click("#login-form button")
        await page.wait_for_selector("#app:not(.hidden) .card")
        print("cards after login:", await page.locator(".card").count())

        await page.click("#new-btn")
        await page.fill("#f-name", "panel-demo")
        await page.select_option("#f-os", "linux")
        await page.fill("#f-proxy", "socks5://user:secret@203.0.113.9:1080")
        await page.click("#modal-root .modal button.btn-accent")
        await page.wait_for_selector(".card:has-text('panel-demo')")
        meta = await page.text_content(".card:has-text('panel-demo') .meta")
        print("panel-demo meta:", meta, "| password hidden:", "secret" not in meta)
        await page.click(".card:has-text('panel-demo') button[title='Sửa']")
        await page.fill("#f-proxy", "")
        await page.click("#modal-root .modal button.btn-accent")
        await page.wait_for_timeout(800)

        await page.click(".card:has-text('mcp-demo') .main-btn")
        await page.wait_for_selector(
            ".card.running:has-text('mcp-demo') .main-btn:has-text('Dừng')", timeout=90_000
        )
        await page.screenshot(path=OUT + r"\panel_list.png")
        print("running cards:", await page.locator(".card.running").count())

        await page.click(".card:has-text('mcp-demo') button[title='Xem màn hình']")
        await page.wait_for_timeout(1500)
        print(
            "viewer class after click:",
            await page.get_attribute("#viewer", "class"),
            "| errors so far:",
            errors,
        )
        print(
            "debug:",
            await page.evaluate("""() => ({app: document.getElementById('app').className,
            login: document.getElementById('login').className, toast: document.getElementById('toast').textContent,
            viewButtons: [...document.querySelectorAll('.card button')].map(b => b.title + '=' + b.textContent)})"""),
        )
        await page.wait_for_selector("#viewer:not(.hidden)")
        await page.fill("#v-url", "https://example.com")
        await page.click("#v-nav button")
        await page.wait_for_function(
            "document.querySelector('#v-tabs button.active')?.textContent.includes('Example')",
            timeout=30_000,
        )
        await page.wait_for_timeout(2500)
        await page.screenshot(path=OUT + r"\panel_viewer.png")
        print("viewer tab:", await page.text_content("#v-tabs button.active"))

        await page.click("#v-close")
        await page.click(".card:has-text('mcp-demo') .main-btn")
        await page.wait_for_selector(".card.running", state="detached", timeout=30_000)
        print("stopped from panel: ok")

        await page.click("[data-lang='en']")
        print("english title:", await page.text_content("main h2"))
        await page.click("[data-lang='vi']")


asyncio.run(main())
print("JS errors:", errors or "none")
