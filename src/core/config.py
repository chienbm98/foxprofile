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
LANGUAGE = _env("LANG", "vi")

API_HOST = _env("API_HOST", "127.0.0.1")
API_PORT = int(_env("API_PORT", "8000"))

# Seconds the API waits for a launched browser to report ready or failed.
LAUNCH_WAIT_TIMEOUT = int(_env("LAUNCH_TIMEOUT", "90"))

FINGERPRINT_FILE = "fingerprint.json"
