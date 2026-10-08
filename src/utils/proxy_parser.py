from urllib.parse import urlparse


def normalize_proxy(proxy_str: str) -> str:
    """Rewrite the provider format host:port:user:pass as user:pass@host:port.

    Anything else (including the URL form) is returned unchanged.
    """
    proxy_str = proxy_str.strip()
    scheme, sep, rest = proxy_str.rpartition("://")
    if "@" in rest:
        return proxy_str
    parts = rest.split(":", 3)
    if len(parts) != 4 or not parts[1].isdigit() or not all(parts):
        return proxy_str
    host, port, user, password = parts
    return f"{scheme}{sep}{user}:{password}@{host}:{port}"


def parse_proxy(proxy_str: str) -> dict | None:
    if not proxy_str or proxy_str == "None":
        return None
    try:
        proxy_str = normalize_proxy(proxy_str)
        if "://" not in proxy_str:
            proxy_str = "http://" + proxy_str
        p = urlparse(proxy_str)
        if not p.hostname or not p.port:
            return None
        cfg = {"server": f"{p.scheme}://{p.hostname}:{p.port}"}
        if p.username:
            cfg["username"] = p.username
        if p.password:
            cfg["password"] = p.password
        return cfg
    except Exception:
        return None


def mask_proxy(proxy_str: str | None) -> str:
    """Proxy as scheme://host:port, without credentials, for display."""
    cfg = parse_proxy(proxy_str or "")
    return cfg["server"] if cfg else ""
