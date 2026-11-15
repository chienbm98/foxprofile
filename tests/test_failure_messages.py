"""What a user reads when a profile change fails: translated, with the detail kept in the log."""

import json

import pytest

from src.core import config
from src.core.errors import ProfileAccountSaveError, ProfileBusyError, ProfileStoreError
from src.core.strings import STRINGS, get_string
from src.services import proton_account
from src.services.profile.manager import ProfileManager
from src.ui.actions.errors import failure_message


def test_a_failed_save_shows_the_translated_message():
    message = failure_message("p", ProfileStoreError("Could not write profiles.json: disk full"))
    assert message == get_string("profile_store_failed")
    assert "disk full" not in message  # the technical detail stays in the log


def test_a_failed_account_save_says_the_profile_was_saved():
    message = failure_message("p", ProfileAccountSaveError("no usable key"))
    assert message == get_string("profile_saved_account_failed")


def test_a_busy_profile_is_named_in_the_message():
    assert failure_message("p", ProfileBusyError("p")) == get_string("busy_profile", name="p")


@pytest.mark.parametrize("key", ["profile_store_failed", "profile_saved_account_failed"])
def test_new_messages_exist_in_both_languages(key):
    assert key in STRINGS["en"]
    assert key in STRINGS["vi"]


def test_a_failed_proton_save_keeps_the_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROFILES_FILE", str(tmp_path / "profiles.json"))
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(config, "PROTON_ACCOUNTS_FILE", str(tmp_path / "proton_accounts.json"))
    monkeypatch.setattr(config, "PROTON_ACCOUNTS_KEY_FILE", str(tmp_path / "proton_accounts.key"))

    def disk_full(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(proton_account, "save", disk_full)
    pm = ProfileManager()
    with pytest.raises(ProfileAccountSaveError):
        pm.add_profile(
            "p",
            "",
            "windows",
            proxy_mode="proton",
            proton_user="user@example.com",
            proton_password="secret",
        )
    # The profile itself was saved, so it stays; only its account is missing.
    assert "p" in pm.profiles
    saved = json.loads((tmp_path / "profiles.json").read_text(encoding="utf-8"))
    assert "p" in saved
