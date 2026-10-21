"""Command line for syncing profiles without the API running.

    python -m src.sync_cli status
    python -m src.sync_cli push gmail-1 [--force]     python -m src.sync_cli push --all
    python -m src.sync_cli pull gmail-1 [--force]     python -m src.sync_cli pull --all

Needs FOXPROFILE_SYNC_URL and FOXPROFILE_SYNC_PASSPHRASE (a .env file works).
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    parser = argparse.ArgumentParser(description="FoxProfile profile sync")
    parser.add_argument("action", choices=["status", "push", "pull"])
    parser.add_argument("name", nargs="?")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    from src.core.container import Container
    from src.services.sync.backends import SyncError

    svc = Container().sync_service
    if not svc.configured:
        print("Set FOXPROFILE_SYNC_URL and FOXPROFILE_SYNC_PASSPHRASE first.", file=sys.stderr)
        return 2
    try:
        if args.action == "status":
            result = svc.status()
        elif args.all:
            result = (svc.push_all if args.action == "push" else svc.pull_all)(args.force)
        elif args.name:
            result = (svc.push if args.action == "push" else svc.pull)(args.name, args.force)
        else:
            parser.error("give a profile name or --all")
    except SyncError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
