"""python -m chrome_engine {fetch,info,open,probe}"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from . import fetch, probe
from .engine import ChromeEngine, EngineError
from .persona import PLATFORMS
from .release import DEFAULT_VERSION, host_os, host_platform


def _progress(done: int, total: int) -> None:
    pct = done * 100 // total if total else 0
    sys.stderr.write(f"\r{done / 1e6:7.1f} / {total / 1e6:.1f} MB  {pct:3d}%")
    if done >= total:
        sys.stderr.write("\n")


def cmd_fetch(args: argparse.Namespace) -> int:
    exe = fetch.install(args.version, progress=_progress)
    print(exe)
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    exe = fetch.installed_executable(args.version)
    print(
        json.dumps(
            {
                "version": args.version or DEFAULT_VERSION,
                "home": str(fetch.engine_home()),
                "host": host_platform(),
                "host_os": host_os(),
                "installed": str(exe) if exe else None,
            },
            indent=2,
        )
    )
    return 0 if exe else 1


def _engine(args: argparse.Namespace) -> ChromeEngine:
    headless: bool | str = args.headless
    if headless in ("true", "false"):
        headless = headless == "true"
    return ChromeEngine(
        args.profile_dir,
        platform=args.platform,
        proxy=args.proxy,
        headless=headless,
        timezone=args.timezone,
        locale=args.locale,
        version=args.version,
    )


async def _open(args: argparse.Namespace) -> int:
    engine = _engine(args)
    context = await engine.start()
    try:
        for warning in engine.warnings:
            print(f"warning: {warning}", file=sys.stderr)
        print(f"persona: {engine.persona}", file=sys.stderr)
        page = context.pages[0] if context.pages else await context.new_page()
        if args.url:
            await page.goto(args.url)
        closed = asyncio.Event()
        context.on("close", lambda _: closed.set())
        await closed.wait()
    finally:
        await engine.stop()
    return 0


async def _probe_and_check(args: argparse.Namespace) -> int:
    engine = _engine(args)
    context = await engine.start()
    try:
        fp = await probe.collect(context)
    finally:
        await engine.stop()
    assert engine.persona is not None
    issues = probe.check(engine.persona, fp)
    if args.json:
        print(json.dumps({"persona": engine.persona.to_json(), "fingerprint": fp}, indent=2))
    print(f"persona: {engine.persona}", file=sys.stderr)
    for warning in engine.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for issue in issues:
        print(f"ISSUE {issue}", file=sys.stderr)
    print(f"{len(issues)} issue(s)", file=sys.stderr)
    return 1 if issues else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m chrome_engine")
    parser.add_argument(
        "--version", default=None, help=f"browser build (default {DEFAULT_VERSION})"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("fetch", help="download and verify the browser build")
    sub.add_parser("info", help="show where the browser is installed")

    for name, helptext in (
        ("open", "open a profile and wait until it is closed"),
        ("probe", "open a profile, print what websites see, check it"),
    ):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("profile_dir")
        p.add_argument("--platform", choices=PLATFORMS, default=None)
        p.add_argument("--proxy", default=None)
        p.add_argument("--timezone", default=None)
        p.add_argument("--locale", default=None)
        p.add_argument("--headless", choices=("true", "false", "offscreen"), default="false")
        if name == "open":
            p.add_argument("--url", default=None)
        else:
            p.add_argument("--json", action="store_true", help="also print the raw fingerprint")

    args = parser.parse_args(argv)
    try:
        if args.command == "fetch":
            return cmd_fetch(args)
        if args.command == "info":
            return cmd_info(args)
        if args.command == "open":
            return asyncio.run(_open(args))
        return asyncio.run(_probe_and_check(args))
    except EngineError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
