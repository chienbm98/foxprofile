"""Timezone and locale from the proxy's exit IP, like Camoufox's geoip=True.

The exit IP is looked up through the proxy bridge (a plain HTTP proxy on
loopback), so SOCKS5 and authenticated upstreams work without PySocks. The IP
is then placed with Camoufox's GeoIP database, the same one FoxProfile uses for
its Camoufox profiles.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExitGeo:
    ip: str
    timezone: str
    locale: str
    latitude: float | None = None
    longitude: float | None = None


def lookup(proxy_url: str | None) -> ExitGeo:
    """Exit IP and its geo, through `proxy_url` (None: this machine's own IP)."""
    from camoufox.geolocation import get_geolocation
    from camoufox.ip import public_ip

    # public_ip is lru_cached for the whole process; a launch must see the current exit.
    fetch_ip = getattr(public_ip, "__wrapped__", public_ip)
    ip = fetch_ip(proxy_url)
    geo = get_geolocation(ip)
    return ExitGeo(
        ip=ip,
        timezone=geo.timezone,
        locale=geo.locale.as_string,
        latitude=geo.latitude,
        longitude=geo.longitude,
    )
