from dataclasses import asdict, dataclass

# Browser engines a profile can run on. A profile keeps its engine for life:
# the two keep incompatible browser data in the same directory.
ENGINES = ("camoufox", "chrome")

# How a profile reaches the internet: direct, a proxy, or the Proton VPN
# extension. Proton mode owns the extension and the per-profile account.
PROXY_MODES = ("direct", "proxy", "proton")

# Operating systems a profile's fingerprint can present.
OS_TYPES = ("windows", "macos", "linux")

# Browser extensions a profile can install: one build per engine, fetched on
# the first launch (see services/browser/extensions.py).
EXTENSION_NAMES = ("proton-vpn",)


def extension_or_none(value: object) -> str | None:
    """A known extension name, or None (unknown values and "" are dropped)."""
    return value if value in EXTENSION_NAMES else None


def proxy_mode_or_default(value: object, proxy: object = None, extension: object = None) -> str:
    """The stored mode, or the one an older profile implies."""
    if value in PROXY_MODES:
        return str(value)
    if extension == "proton-vpn":
        return "proton"
    return "proxy" if proxy else "direct"


def country_or_none(value: object) -> str:
    """A two-letter country code, uppercased; "" means Quick Connect."""
    code = str(value or "").strip().upper()
    return code if len(code) == 2 and code.isalpha() else ""


@dataclass
class Profile:
    name: str
    proxy: str | None = None
    os_type: str = "windows"
    # None = follow the proxy's exit IP (Camoufox geoip); set to pin a value.
    timezone: str | None = None
    locale: str | None = None
    engine: str = "camoufox"
    # Derived from proxy_mode: the Proton VPN extension is installed only in
    # proton mode.
    extension: str | None = None
    # direct | proxy | proton
    proxy_mode: str = "direct"
    # Proton exit country (ISO code); "" = Quick Connect (fastest).
    proton_country: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
