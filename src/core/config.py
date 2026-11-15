import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _env(key: str, default: str) -> str:
    """Read the FOXPROFILE_<key> environment variable."""
    return os.getenv(f"FOXPROFILE_{key}", default)


PROFILES_FILE = _env("PROFILES_FILE", "profiles.json")
DATA_DIR = _env("DATA_DIR", "camoufox_data")


def profile_data_dir(name: str) -> str:
    """A profile's browser data directory. DATA_DIR is relative to the working directory."""
    return os.path.join(os.getcwd(), DATA_DIR, name)


LOG_DIR = _env("LOG_DIR", "logs")
LOG_LEVEL = _env("LOG_LEVEL", "INFO")
PROXY_CHECK_TIMEOUT = int(_env("PROXY_TIMEOUT", "10"))
LANGUAGE = _env("LANG", "en")


def _api_host(value: str) -> str:
    """A blank host falls back to loopback, never to "all interfaces"."""
    return value.strip() or "127.0.0.1"


API_HOST = _api_host(_env("API_HOST", "127.0.0.1"))
API_PORT = int(_env("API_PORT", "8000"))

# Seconds the API waits for a launched browser to report ready or failed.
LAUNCH_WAIT_TIMEOUT = int(_env("LAUNCH_TIMEOUT", "180"))

FINGERPRINT_FILE = "fingerprint.json"


def _headless(value: str) -> bool | str:
    """'true'/'false', or 'virtual' (Linux: hidden Xvfb display, more stealthy)."""
    value = value.strip().lower()
    if value == "virtual":
        return "virtual"
    return value in ("1", "true", "yes")


# Browsers open hidden when true; server mode turns this on by default.
HEADLESS = _headless(_env("HEADLESS", "false"))

# Reopen the tabs a profile had open when it was last stopped.
RESTORE_TABS = _env("RESTORE_TABS", "true").strip().lower() in ("1", "true", "yes")

# Shared secret for the REST API, the web panel and the MCP server. Required
# whenever the API listens on anything other than the loopback interface.
API_TOKEN = _env("API_TOKEN", "")

# Proton VPN accounts used for the extension's automatic sign-in. Entered per
# profile in the profile dialog, stored encrypted next to profiles.json.
PROTON_ACCOUNTS_FILE = _env("PROTON_ACCOUNTS_FILE", "proton_accounts.json")
PROTON_ACCOUNTS_KEY_FILE = _env("PROTON_ACCOUNTS_KEY_FILE", "proton_accounts.key")
# How long a successful sign-in stays in the profile's diagnostic marker.
PROTON_LOGIN_DAYS = int(_env("PROTON_LOGIN_DAYS", "7"))
