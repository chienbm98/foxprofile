"""Cookie export/import for stopped profiles.

Cookies travel between three shapes:
- Playwright: what cookie_tool.py reads from and writes to the browser.
- JSON in the EditThisCookie / Cookie-Editor layout, which GoLogin, GPM,
  Multilogin and the Cookie-Editor extension import directly.
- Netscape cookies.txt, used by yt-dlp, curl and wget.
"""

import json
import os
import pathlib
import subprocess
import sys
import time
from typing import Any

from ...core.logging import get_logger

logger = get_logger("browser.cookies")

_TOOL = os.path.join(pathlib.Path(__file__).parent, "cookie_tool.py")
_PROJECT_ROOT = str(pathlib.Path(__file__).resolve().parents[3])
_TIMEOUT = 120

_SAMESITE_TO_EXT = {"Strict": "strict", "Lax": "lax", "None": "no_restriction"}
_SAMESITE_FROM_EXT = {
    "strict": "Strict",
    "lax": "Lax",
    "no_restriction": "None",
    "none": "None",
}

FORMATS = ("json", "netscape")

# Firefox drops session cookies when the browser closes, so an imported
# session cookie would vanish before the profile is ever opened. Imported
# session cookies get this lifetime instead.
_SESSION_COOKIE_TTL = 365 * 24 * 3600


class CookieError(Exception):
    pass


def _call_tool(action: str, profile_name: str, os_type: str, stdin: str = "") -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = _PROJECT_ROOT + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    try:
        proc = subprocess.run(
            [sys.executable, _TOOL, action, profile_name, os_type],
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_TIMEOUT,
            cwd=pathlib.Path.cwd(),
            env=env,
        )
    except subprocess.TimeoutExpired as e:
        raise CookieError(f"Cookie {action} timed out after {_TIMEOUT}s") from e

    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT:")]
    if not lines:
        tail = (proc.stderr or proc.stdout).strip()[-300:]
        raise CookieError(f"Cookie {action} failed: {tail or 'no output'}")
    result = json.loads(lines[-1].removeprefix("RESULT:"))
    if "error" in result:
        raise CookieError(result["error"])
    return result


# --- Format conversion -------------------------------------------------------


def _to_extension_json(cookies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for i, c in enumerate(cookies, start=1):
        expires = c.get("expires", -1)
        session = expires is None or expires < 0
        item = {
            "domain": c["domain"],
            "hostOnly": not c["domain"].startswith("."),
            "httpOnly": bool(c.get("httpOnly")),
            "name": c["name"],
            "path": c.get("path", "/"),
            "sameSite": _SAMESITE_TO_EXT.get(c.get("sameSite", ""), "unspecified"),
            "secure": bool(c.get("secure")),
            "session": session,
            "storeId": "0",
            "value": c["value"],
            "id": i,
        }
        if not session:
            item["expirationDate"] = expires
        out.append(item)
    return out


def _to_netscape(cookies: list[dict[str, Any]]) -> str:
    lines = ["# Netscape HTTP Cookie File", "# Exported by FoxProfile", ""]
    for c in cookies:
        domain = c["domain"]
        if c.get("httpOnly"):
            domain = "#HttpOnly_" + domain
        expires = c.get("expires", -1)
        lines.append(
            "\t".join(
                [
                    domain,
                    "TRUE" if c["domain"].startswith(".") else "FALSE",
                    c.get("path", "/"),
                    "TRUE" if c.get("secure") else "FALSE",
                    str(int(expires)) if expires and expires > 0 else "0",
                    c["name"],
                    c["value"],
                ],
            ),
        )
    return "\n".join(lines) + "\n"


def _as_timestamp(value: Any) -> float:
    """Expiry as epoch seconds, or -1 when missing or not a number."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0


def _from_json(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cookies = []
    for item in items:
        if not isinstance(item, dict) or not item.get("name") or not item.get("domain"):
            continue
        domain = item["domain"]
        if item.get("hostOnly") is False and not domain.startswith("."):
            domain = "." + domain
        # Extension layout uses expirationDate; Playwright layout uses expires.
        expires = item.get("expirationDate", item.get("expires"))
        same_site = item.get("sameSite")
        if same_site not in ("Strict", "Lax", "None"):
            same_site = _SAMESITE_FROM_EXT.get(str(same_site).lower(), "Lax")
        cookie = {
            "name": item["name"],
            "value": str(item.get("value", "")),
            "domain": domain,
            "path": item.get("path") or "/",
            "httpOnly": bool(item.get("httpOnly")),
            "secure": bool(item.get("secure")) or same_site == "None",
            "sameSite": same_site,
        }
        expiry = _as_timestamp(expires)
        if expiry > 0 and not item.get("session"):
            cookie["expires"] = expiry
        else:
            cookie["expires"] = time.time() + _SESSION_COOKIE_TTL
        cookies.append(cookie)
    return cookies


def _from_netscape(text: str) -> list[dict[str, Any]]:
    cookies = []
    for raw in text.splitlines():
        line = raw.strip()
        http_only = line.startswith("#HttpOnly_")
        if http_only:
            line = line.removeprefix("#HttpOnly_")
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 7:
            continue
        domain, _subdomains, path, secure, expires, name, value = parts
        cookie = {
            "name": name,
            "value": value,
            "domain": domain,
            "path": path or "/",
            "httpOnly": http_only,
            "secure": secure.upper() == "TRUE",
            "sameSite": "Lax",
        }
        if expires.isdigit() and int(expires) > 0:
            cookie["expires"] = float(expires)
        else:
            cookie["expires"] = time.time() + _SESSION_COOKIE_TTL
        cookies.append(cookie)
    return cookies


def parse_cookies(text: str) -> list[dict[str, Any]]:
    """Parse JSON (extension or Playwright layout) or Netscape cookies.txt."""
    stripped = text.strip()
    if stripped.startswith(("[", "{")):
        try:
            data = json.loads(stripped)
        except ValueError as e:
            raise CookieError(f"Invalid cookie JSON: {e}") from e
        if isinstance(data, dict):
            data = data.get("cookies", [data])
        if not isinstance(data, list):
            raise CookieError("Cookie JSON must be a list of cookies")
        return _from_json(data)
    return _from_netscape(text)


# --- Public API --------------------------------------------------------------


def export_cookies(profile_name: str, os_type: str, fmt: str = "json") -> tuple[str, int]:
    """Return (text, count) of a stopped profile's cookies in `fmt`."""
    if fmt not in FORMATS:
        raise CookieError(f"Unknown format '{fmt}'. Use one of: {', '.join(FORMATS)}")
    cookies = _call_tool("export", profile_name, os_type)["cookies"]
    logger.info("Exported %d cookies from %s (%s)", len(cookies), profile_name, fmt)
    if fmt == "netscape":
        return _to_netscape(cookies), len(cookies)
    return json.dumps(_to_extension_json(cookies), indent=2, ensure_ascii=False), len(
        cookies,
    )


def import_cookies(profile_name: str, os_type: str, text: str) -> int:
    """Add cookies from JSON or Netscape text to a stopped profile."""
    cookies = parse_cookies(text)
    if not cookies:
        raise CookieError("No valid cookies found in the input")
    result = _call_tool("import", profile_name, os_type, json.dumps(cookies))
    logger.info("Imported %d cookies into %s", result["imported"], profile_name)
    return result["imported"]
