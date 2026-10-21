"""Tell whether a profile is still logged in to Gmail, and as whom.

Opens the inbox in the running profile and reads where Google sent it: the inbox
(logged in) or a sign-in / marketing page (logged out). The signed-in address is
read from the inbox tab title ("Inbox (3) - name@gmail.com - Gmail"), which does not
depend on the interface language.
"""

from __future__ import annotations

import re
import time
import urllib.parse
from typing import Any

INBOX_URL = "https://mail.google.com/mail/u/0/#inbox"
_EMAIL = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")
_SIGNED_OUT_HOSTS = ("accounts.google.com", "workspace.google.com", "www.google.com")


def classify(url: str, title: str) -> dict[str, Any]:
    """state is alive, logged_out or unknown; email only when logged in."""
    parsed = urllib.parse.urlparse(url)
    host, path = parsed.netloc, parsed.path
    if host == "mail.google.com" and path.startswith("/mail/"):
        match = _EMAIL.search(title or "")
        return {"state": "alive", "email": match.group(0).lower() if match else None}
    if host in _SIGNED_OUT_HOSTS or "signin" in path:
        return {"state": "logged_out", "email": None}
    return {"state": "unknown", "email": None}


def check(control, name: str, settle: float = 5.0, retries: int = 3) -> dict[str, Any]:
    """Run the check in an already running profile. `control` is launcher.control."""
    control(name, "navigate", {"url": INBOX_URL})
    result: dict[str, Any] = {"state": "unknown", "email": None}
    for _ in range(retries):
        time.sleep(settle)
        page = control(
            name, "evaluate", {"script": "({url: location.href, title: document.title})"}
        )
        info = page["result"]
        result = classify(info["url"], info["title"])
        if result["state"] != "unknown":
            break
    return result
