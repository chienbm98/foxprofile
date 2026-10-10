"""Command line for agents and schedulers: one macro per call, its result as JSON on stdout.

    python -m tqd_automation post facebook --profile P --text-file F [--media M ...]
        [--audience default|only_me] [--dry-run]
    python -m tqd_automation post tiktok --profile P --text-file F --media M [...]
        [--visibility default|only_me] [--dry-run]
    python -m tqd_automation post x --profile P --text-file F [--media M ...] [--dry-run]
    python -m tqd_automation status
    python -m tqd_automation state --profile P --platform facebook|tiktok|x

The post text is read from a UTF-8 file, never from argv, so Vietnamese text and newlines survive
the shell. Exit codes: 0 published / dry_run / awaiting_approval, 2 blocked, 3 needs_agent,
1 failed or error (argparse also exits 2 on a usage error, with the message on stderr).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from . import client, overview
from .guards import Guards
from .platforms import facebook, tiktok, x
from .result import PostResult

EXIT_CODES = {
    "published": 0,
    "dry_run": 0,
    "awaiting_approval": 0,
    "blocked": 2,
    "needs_agent": 3,
    "failed": 1,
}
PLATFORMS = ("facebook", "tiktok", "x")
VISIBILITY = ("default", "only_me")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tqd_automation")
    commands = parser.add_subparsers(dest="command", required=True)

    post = commands.add_parser("post", help="publish one post")
    platforms = post.add_subparsers(dest="platform", required=True)
    for name in PLATFORMS:
        p = platforms.add_parser(name)
        p.add_argument("--profile", required=True)
        p.add_argument("--text-file", required=True, help="UTF-8 file holding the post text")
        p.add_argument("--media", nargs="+", default=[], required=name == "tiktok")
        p.add_argument("--dry-run", action="store_true", help="fill everything, never press Post")
        if name == "facebook":
            p.add_argument("--audience", choices=VISIBILITY, default="default")
        if name == "tiktok":
            p.add_argument("--visibility", choices=VISIBILITY, default="default")

    commands.add_parser("status", help="caps, waits, lockouts and recent ledger lines")

    state = commands.add_parser("state", help="judge the page open in a profile")
    state.add_argument("--profile", required=True)
    state.add_argument("--platform", choices=PLATFORMS, required=True)
    return parser


def _post(args: argparse.Namespace) -> PostResult:
    try:
        text = Path(args.text_file).read_text(encoding="utf-8-sig")  # Notepad may add a BOM
    except OSError as e:
        return PostResult("failed", detail=f"cannot read text file: {e}")
    if not text.strip():
        return PostResult("failed", detail="text file is empty")

    common = {"profile": args.profile, "dry_run": args.dry_run}
    if args.platform == "facebook":
        return facebook.post(text=text, images=args.media, audience=args.audience, **common)
    if args.platform == "tiktok":
        return tiktok.post(caption=text, media=args.media, visibility=args.visibility, **common)
    return x.post(text=text, media=args.media, **common)


def _print(data: object) -> None:
    sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main(argv: list[str] | None = None, guards: Guards | None = None) -> int:
    args = _parser().parse_args(argv)
    client.configure_from_env()
    if args.command == "post":
        result = _post(args)
        _print(asdict(result))
        return EXIT_CODES[result.status]
    try:
        if args.command == "status":
            _print(overview.automation_status(guards))
        else:
            _print(overview.page_state(args.profile, args.platform))
    except Exception as e:  # report as JSON so a calling agent can read it
        _print({"status": "failed", "detail": str(e)[:300]})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
