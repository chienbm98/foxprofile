import os
from pathlib import Path

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "browser: launches the real fingerprint-chromium build (skipped when not installed)",
    )


@pytest.fixture(scope="session")
def chrome_exe() -> Path:
    """The installed browser, or skip. FOXPROFILE_CHROME_EXECUTABLE overrides it."""
    override = os.getenv("FOXPROFILE_CHROME_EXECUTABLE")
    if override:
        return Path(override)
    from chrome_engine.fetch import installed_executable

    exe = installed_executable()
    if exe is None:
        pytest.skip("fingerprint-chromium not installed (python -m chrome_engine fetch)")
    return exe
