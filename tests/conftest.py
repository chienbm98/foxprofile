import os
import tempfile

# Keep the auto-generated token out of the checkout.
os.environ.setdefault("FOXPROFILE_TOKEN_FILE", os.path.join(tempfile.mkdtemp(), ".api_token"))
# Messages are asserted in English whatever the developer machine speaks.
os.environ.setdefault("FOXPROFILE_LANG", "en")

import pytest  # noqa: E402

from src.api import app, auth  # noqa: E402


@pytest.fixture(autouse=True)
def _tokenless_api(monkeypatch):
    """Unit tests exercise the API in its token-less, loopback-only mode;
    test_api_auth sets its own token."""
    monkeypatch.setattr(auth, "API_TOKEN", "")
    monkeypatch.setattr(app, "API_TOKEN", "")
