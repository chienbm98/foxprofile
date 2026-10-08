"""Open the web panel's MCP guide, switch clients, insert the token, copy, and screenshot it."""

import asyncio
import json
import os
import pathlib
import time
import urllib.request

from camoufox.async_api import AsyncCamoufox

OUT_DIR = pathlib.Path(os.getenv("E2E_OUT", "e2e-output"))
OUT_DIR.mkdir(exist_ok=True)

URL = os.getenv("FOXPROFILE_URL", "http://127.0.0.1:8000").rstrip("/") + "/"
TOKEN = os.environ.get("FOXPROFILE_API_TOKEN", "")
OUT = str(OUT_DIR)
errors = []

for _ in range(60):
    try:
        urllib.request.urlopen(URL + "api/v1/health", timeout=2)
        break
    except Exception:
        time.sleep(1)


async def main():
    async with AsyncCamoufox(headless=True, os="windows") as browser:
        page = await browser.new_page(viewport={"width": 1400, "height": 1000})
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(URL)
        await page.fill("#token", TOKEN)
        await page.click("#login-form button")
        await page.wait_for_selector("#app:not(.hidden)")

        await page.click("#mcp-btn")
        await page.wait_for_selector("pre.code")
        print("endpoint:", await page.text_content("#modal-root code"))
        code = await page.text_content("pre.code")
        print("claude-code:", code)
        print("placeholder before insert:", "<FOXPROFILE_API_TOKEN>" in code)

        await page.check("#modal-root input[type=checkbox]")
        code = await page.text_content("pre.code")
        print("token inserted:", TOKEN in code and "<FOXPROFILE_API_TOKEN>" not in code)

        await page.click(".chips button:has-text('Cursor')")
        cursor = json.loads(await page.text_content("pre.code"))
        print("cursor json valid:", cursor["mcpServers"]["foxprofile"]["url"])

        await page.click(".chips button:has-text('Claude Desktop')")
        print("desktop note:", (await page.text_content("#modal-root .note"))[:70])
        await page.click(".chips button:has-text('Claude Code')")
        await page.uncheck("#modal-root input[type=checkbox]")
        await page.click(".where-row .btn-accent")
        await page.wait_for_timeout(300)
        print(
            "copy status:", (await page.text_content("#modal-root .modal > div:nth-last-child(2)"))
        )
        await page.screenshot(path=OUT + r"\guide_panel.png")


asyncio.run(main())
print("JS errors:", errors or "none")
