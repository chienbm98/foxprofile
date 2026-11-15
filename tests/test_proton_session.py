"""The Proton session CLI helpers (no browser)."""

import json
import stat

import pytest

from src.models.profile import Profile
from src.services import proton_session


def test_session_file_round_trip(tmp_path):
    path = tmp_path / "session.json"
    payload = {"uid": "u", "accessToken": "a", "refreshToken": "r"}
    proton_session._write_session(path, payload)
    assert proton_session._read_session(path) == payload
    if hasattr(stat, "S_IMODE"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_session_file_requires_tokens(tmp_path):
    path = tmp_path / "session.json"
    path.write_text(json.dumps({"uid": "u"}), encoding="utf-8")
    with pytest.raises(ValueError):
        proton_session._read_session(path)


def test_country_is_normalised_and_validated():
    profile = Profile(name="p")
    assert proton_session._country("us", profile) == "US"
    assert proton_session._country("", profile) == ""
    with pytest.raises(SystemExit):
        proton_session._country("ZZ", profile)


def test_require_rejects_a_non_chrome_engine():
    with pytest.raises(SystemExit):
        proton_session._require(Profile(name="p", proxy_mode="proton"), "p")


def test_require_rejects_a_non_proton_profile():
    with pytest.raises(SystemExit):
        proton_session._require(Profile(name="p", engine="chrome", proxy_mode="proxy"), "p")


def test_require_accepts_a_chrome_proton_profile():
    profile = Profile(name="p", engine="chrome", proxy_mode="proton")
    assert proton_session._require(profile, "p") is profile
