"""Timezone and locale from the proxy's exit IP, like Camoufox's geoip=True.

The exit IP is looked up through the proxy bridge (a plain HTTP proxy on
loopback), so SOCKS5 and authenticated upstreams work without PySocks. The IP
is then placed with Camoufox's GeoIP database, the same one FoxProfile uses for
its Camoufox profiles.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# Which locale a profile showed for the country it was last in (see remembered_locale).
GEO_LOCALE_FILE = "geo_locale.json"
_LOCALE = re.compile(r"^[a-z]{2,3}(-[A-Z][a-z]{3})?(-[A-Z]{2}|-\d{3})?$")


@dataclass(frozen=True)
class ExitGeo:
    ip: str
    timezone: str
    locale: str
    latitude: float | None = None
    longitude: float | None = None
    # ISO country code of the exit IP, e.g. "US".
    country: str | None = None


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
        country=geo.locale.region,
    )


def kept_locale(profile_dir: str | Path, country: str | None) -> str | None:
    """The locale the profile keeps for `country`, if it has been there before."""
    if not country:
        return None
    try:
        saved = json.loads((Path(profile_dir) / GEO_LOCALE_FILE).read_text(encoding="utf-8"))
        locale = saved.get("locale")
        if saved.get("country") == country and isinstance(locale, str) and _LOCALE.match(locale):
            return locale
    except (OSError, ValueError, AttributeError):
        pass
    return None


def remembered_locale(profile_dir: str | Path, country: str | None, locale: str) -> str:
    """The locale the profile showed before in `country`, else `locale` (then remembered).

    Camoufox's GeoIP picks the language for a country at random, weighted by how
    many people speak it, on every lookup: the same profile would come back as
    en-US one day and es-US the next. The first pick is kept until the exit IP
    moves to another country.
    """
    if not country:
        return locale
    kept = kept_locale(profile_dir, country)
    if kept:
        return kept
    path = Path(profile_dir) / GEO_LOCALE_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"country": country, "locale": locale}), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass
    return locale
