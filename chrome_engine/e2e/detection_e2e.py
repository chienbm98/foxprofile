"""Manual check: the Chrome engine against public bot-detection pages.

Needs the internet and the installed browser, so it is not part of pytest:

    python chrome_engine/e2e/detection_e2e.py headed headless [--proxy URL]

Uses a throwaway profile directory. The same pages as tests/e2e/detection_e2e.py
(Camoufox), plus CreepJS, so both engines can be compared side by side.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from chrome_engine import probe
from chrome_engine.engine import ChromeEngine

CHECKS = [
    (
        "sannysoft",
        "https://bot.sannysoft.com/",
        6,
        "() => { const f = [...document.querySelectorAll('td.failed')].map(t => t.parentElement.innerText.replace(/\\s+/g,' ').slice(0,50)); return f.length ? f : 'all passed'; }",
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
    (
        "creepjs",
        "https://abrahamjuliot.github.io/creepjs/",
        20,
        "() => { const t = document.body.innerText.replace(/\\s+/g,' '); return [t.match(/\\d+% like headless/)?.[0], t.match(/\\d+% headless/)?.[0], t.match(/lies \\(\\d+\\)/)?.[0], t.match(/trash \\(\\d+\\)/)?.[0]].filter(Boolean).join(' | ') || t.slice(0, 120); }",
    ),
]


async def run(headless: bool | str, proxy: str | None) -> None:
    with tempfile.TemporaryDirectory() as profile_dir:
        engine = ChromeEngine(profile_dir, headless=headless, proxy=proxy)
        context = await engine.start()
        try:
            print(f"  persona          {engine.persona}")
            for warning in engine.warnings:
                print(f"  warning          {warning}")
            issues = probe.check(engine.persona, await probe.collect(context))
            print(f"  self-check       {'ok' if not issues else '; '.join(map(str, issues))}")
            page = context.pages[0]
            for name, url, wait, js in CHECKS:
                try:
                    await page.goto(url, timeout=45_000)
                    await page.wait_for_timeout(wait * 1000)
                    result = await page.evaluate(js)
                except Exception as e:
                    result = f"ERROR {type(e).__name__}: {str(e)[:80]}"
                print(f"  {name:16} {result}")
            if engine.crashes:
                print(f"  CRASHED          {engine.crashes}")
        finally:
            await engine.stop()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("modes", nargs="+", choices=["headed", "headless", "offscreen"])
    parser.add_argument("--proxy", default=None)
    args = parser.parse_args()
    for mode in args.modes:
        print(f"== {mode}")
        headless = {"headed": False, "headless": True, "offscreen": "offscreen"}[mode]
        await run(headless, args.proxy)


if __name__ == "__main__":
    asyncio.run(main())
