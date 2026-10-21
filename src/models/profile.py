from dataclasses import asdict, dataclass, field

# Browser engines a profile can run on. A profile keeps its engine for life:
# the two keep incompatible browser data in the same directory.
ENGINES = ("camoufox", "chrome")

# Last known result of the Gmail session check.
SESSION_STATES = ("alive", "logged_out", "needs_verification", "unknown")

# How automatic re-login treats the account: type email and password, type the email only,
# or never touch the sign-in page.
LOGIN_MODES = ("full", "email_only", "manual")


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
    # Encrypted `FPV1:` tokens keyed by vault.SECRET_FIELDS; never plain text.
    secrets: dict[str, str] = field(default_factory=dict)
    login_mode: str = "full"
    # Re-login by itself when the session is lost (session check, launch, scheduled task).
    auto_login: bool = False

    def to_dict(self) -> dict:
        return asdict(self)
