"""Human-readable sync log: one line per event, and a snapshot file that is easy to send."""

from __future__ import annotations

import platform
import sys
import time
from typing import Any

STEPS = ("check_s", "pack_s", "encrypt_s", "upload_s", "download_s", "decrypt_s", "import_s")


def format_event(e: dict[str, Any]) -> str:
    when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e.get("t", time.time())))
    kind = str(e.get("event", "")).replace("sync_", "")
    parts = [
        when,
        f"{kind:<14}",
        f"{e.get('profile') or '-':<16}",
        f"[{e.get('trigger') or '-'}]",
        "ok" if e.get("ok", True) else "FAILED",
    ]
    if e.get("version") is not None:
        parts.append(f"v{e['version']}")
    if e.get("bytes"):
        parts.append(f"{e['bytes'] / 1024:.0f}KB")
    if e.get("total_s") is not None:
        parts.append(f"total={e['total_s']}s")
    steps = " ".join(f"{k[:-2]}={e[k]}s" for k in STEPS if e.get(k) is not None)
    if steps:
        parts.append(steps)
    for key in ("skipped", "reason", "error"):
        if e.get(key):
            parts.append(f"{key}={e[key]}")
    if e.get("store"):
        parts.append(f"store={e['store']}")
    if e.get("machine"):
        parts.append(f"machine={e['machine']}")
    return "  ".join(parts)


def snapshot_text(events: list[dict[str, Any]], header: dict[str, Any]) -> str:
    """Oldest first, with a header that says where and on what the numbers were taken."""
    lines = [
        "FoxProfile sync log",
        f"saved:    {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"machine:  {header.get('machine')}",
        f"store:    {header.get('store') or '(none resolved)'}",
        f"system:   {platform.platform()}  Python {sys.version.split()[0]}",
        f"events:   {len(events)} (newest at the bottom)",
    ]
    for row in header.get("profiles", []):
        lines.append(
            f"profile:  {row['name']}  {row['state']}  local v{row['local_version']}"
            f"  remote v{row['remote_version']}  auto={row['auto']}"
        )
    lines.append("")
    lines += [format_event(e) for e in reversed(events)]
    return "\n".join(lines) + "\n"
