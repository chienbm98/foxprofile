"""HTTP calls from FoxProfile to its own processes (the API, a browser's control server).

urllib sends every request through HTTP_PROXY / HTTPS_PROXY unless NO_PROXY
covers the host. On a machine with a proxy variable set, 127.0.0.1 would then
be routed through that proxy and the call would fail. Loopback URLs therefore
use an opener without proxies; every other URL keeps the default behaviour.
"""

from __future__ import annotations

import ipaddress
import urllib.request
from typing import Any
from urllib.parse import urlsplit

_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def is_loopback_url(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def open_url(request: urllib.request.Request, timeout: float) -> Any:
    """Open `request`. Loopback addresses ignore proxy settings from the environment."""
    if is_loopback_url(request.full_url):
        return _DIRECT.open(request, timeout=timeout)
    return urllib.request.urlopen(request, timeout=timeout)
