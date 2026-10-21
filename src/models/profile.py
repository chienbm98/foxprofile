from dataclasses import asdict, dataclass, field

# Browser engines a profile can run on. A profile keeps its engine for life:
# the two keep incompatible browser data in the same directory.
ENGINES = ("camoufox", "chrome")

# Last known result of the Gmail session check.
SESSION_STATES = ("alive", "logged_out", "unknown")


@dataclass
class Profile:
    name: str
    proxy: str | None = None
    os_type: str = "windows"
    # None = follow the proxy's exit IP (Camoufox geoip); set to pin a value.
    timezone: str | None = None
    locale: str | None = None
    engine: str = "camoufox"
    # What the profile is for; travels with the profile through export and sync.
    email: str | None = None
    purpose: str | None = None
    notes: str | None = None
    tags: list[str] = field(default_factory=list)
    session_state: str | None = None
    session_checked_at: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)
