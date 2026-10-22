"""Export profiles to one encrypted file, or import such a file, without the server running.

    python -m src.transfer_cli export profiles.fpbundle [profile ...]   (all profiles if none given)
    python -m src.transfer_cli import profiles.fpbundle [--overwrite]

The passphrase comes from the OS credential store or FOXPROFILE_SYNC_PASSPHRASE, or --passphrase.
Stop the profiles first; run it from the folder that holds profiles.json (run\\machineA).
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    parser = argparse.ArgumentParser(description="FoxProfile profile export and import")
    parser.add_argument("action", choices=["export", "import"])
    parser.add_argument("file")
    parser.add_argument("names", nargs="*")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--passphrase")
    args = parser.parse_args()

    from src.services.profile import bundle
    from src.services.profile.manager import ProfileManager
    from src.services.vault import vault

    passphrase = args.passphrase or vault.get_passphrase()
    pm = ProfileManager()
    try:
        if args.action == "export":
            result = bundle.export_bundle(pm, args.names, passphrase, args.file)
        else:
            result = bundle.import_bundle(pm, args.file, passphrase, args.overwrite)
    except bundle.BundleError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
