"""Read or write a stopped profile's cookies through a headless Camoufox.

Run as a subprocess (like runner.py) so the async browser gets its own event
loop. Usage:
    python cookie_tool.py export <profile> <os>
    python cookie_tool.py import <profile> <os>   (Playwright cookies JSON on stdin)

The last stdout line is "RESULT:<json>".
"""

import asyncio
import json
import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

from camoufox.async_api import AsyncCamoufox

from src.core.config import DATA_DIR
from src.services.browser.fingerprint import load_or_create
from src.utils.validation import validate_profile_name


async def _run(action: str, profile_name: str, os_type: str, payload: list) -> dict:
    profile_dir = os.path.join(os.getcwd(), DATA_DIR, profile_name)
    async with AsyncCamoufox(
        headless=True,
        os=os_type,
        fingerprint=load_or_create(profile_dir, os_type),
        user_data_dir=profile_dir,
        persistent_context=True,
    ) as context:
        if action == "export":
            return {"cookies": await context.cookies()}
        await context.add_cookies(payload)
        return {"imported": len(payload)}


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) != 4 or sys.argv[1] not in ("export", "import"):
        print('RESULT:{"error": "usage: cookie_tool.py export|import <profile> <os>"}')
        return 2

    action, profile_name, os_type = sys.argv[1:]
    valid, msg = validate_profile_name(profile_name)
    if not valid or os_type not in ("windows", "macos", "linux"):
        print("RESULT:" + json.dumps({"error": msg or f"invalid os {os_type!r}"}))
        return 2
    payload = json.loads(sys.stdin.read() or "[]") if action == "import" else []
    try:
        result = asyncio.run(_run(action, profile_name, os_type, payload))
    except Exception as e:
        print("RESULT:" + json.dumps({"error": f"{type(e).__name__}: {e}"}))
        return 1
    print("RESULT:" + json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
