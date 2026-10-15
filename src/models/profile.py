from dataclasses import asdict, dataclass, field

# Browser engines a profile can run on. A profile keeps its engine for life:
# the two keep incompatible browser data in the same directory.
ENGINES = ("camoufox", "chrome")


@dataclass
class Profile:
    name: str
    proxy: str | None = None
    os_type: str = "windows"
    # None = follow the proxy's exit IP (Camoufox geoip); set to pin a value.
    # When set they are also the "custom" value of the timezone / language settings.
    timezone: str | None = None
    locale: str | None = None
    engine: str = "camoufox"
    # Fingerprint settings {item: {"mode", "value"}} (services/browser/fpsettings.py);
    # the modes each engine honours differ, so they are clamped per engine.
    fingerprint: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        from ..services.browser import fpsettings

        self.fingerprint = fpsettings.tolerant(self.fingerprint, self.os_type, self.engine)

    def to_dict(self) -> dict:
        return asdict(self)
