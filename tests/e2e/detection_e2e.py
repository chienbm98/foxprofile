"""Compare Camoufox headed vs headless against common bot checks, with FoxProfile-style config."""

import asyncio
import sys

from camoufox.async_api import AsyncCamoufox
from camoufox.fingerprints import generate_fingerprint

CHECKS = [
    (
        "sannysoft",
        "https://bot.sannysoft.com/",
        6,
        "() => [...document.querySelectorAll('td.failed')].map(t => t.parentElement.innerText.replace(/\\s+/g,' ').slice(0,50))",
    ),
    (
        "areyouheadless",
        "https://arh.antoinevastel.com/bots/areyouheadless",
        6,
        "() => document.querySelector('#res')?.innerText || document.body.innerText.slice(0,120)",
    ),
    (
        "cloudflare",
        "https://www.scrapingcourse.com/cloudflare-challenge",
        15,
        "() => document.body.innerText.replace(/\\s+/g,' ').slice(0,90)",
    ),
    (
        "browserscan-bot",
        "https://www.browserscan.net/bot-detection",
        12,
        "() => document.body.innerText.replace(/\\s+/g,' ').match(/(Test Results|Normal|Robot)[^.]{0,80}/)?.[0] || 'n/a'",
    ),
]


async def run(headless):
    fp = generate_fingerprint(os="windows")
    async with AsyncCamoufox(
        headless=headless, os="windows", fingerprint=fp, humanize=True, geoip=True
    ) as browser:
        page = await browser.new_page()
        for name, url, wait, js in CHECKS:
            try:
                await page.goto(url, timeout=45_000)
                await page.wait_for_timeout(wait * 1000)
                result = await page.evaluate(js)
            except Exception as e:
                result = f"ERROR {type(e).__name__}"
            print(f"  {name:16} {result}")


async def main():
    for mode in sys.argv[1:]:
        headless = {"headed": False, "headless": True}[mode]
        print(f"== {mode}")
        await run(headless)


asyncio.run(main())
