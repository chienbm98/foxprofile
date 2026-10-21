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
LOG_DIR = _env("LOG_DIR", "logs")
LOG_LEVEL = _env("LOG_LEVEL", "INFO")
PROXY_CHECK_TIMEOUT = int(_env("PROXY_TIMEOUT", "10"))
LANGUAGE = _env("LANG", "en")

API_HOST = _env("API_HOST", "127.0.0.1")
API_PORT = int(_env("API_PORT", "8000"))

# Seconds the API waits for a launched browser to report ready or failed.
LAUNCH_WAIT_TIMEOUT = int(_env("LAUNCH_TIMEOUT", "90"))

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

# Profile sync: a folder path, webdav(s)://host/path or s3://bucket/prefix. Archives are
# encrypted with FOXPROFILE_SYNC_PASSPHRASE (read from the environment only).
SYNC_URL = _env("SYNC_URL", "")
SYNC_PASSPHRASE = _env("SYNC_PASSPHRASE", "")
SYNC_STATE_FILE = _env("SYNC_STATE_FILE", "sync_state.json")
MACHINE_NAME = _env("MACHINE_NAME", "")
AUTOMATION_FILE = _env("AUTOMATION_FILE", "automation.json")
ACTIVITY_LOG = _env("ACTIVITY_LOG", "activity.jsonl")

# "true": pull a newer copy before launching a profile and push it when it stops.
SYNC_AUTO = _env("SYNC_AUTO", "false").strip().lower() in ("1", "true", "yes")
