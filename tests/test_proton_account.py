"""The per-profile Proton account store: encryption, updates and clearing."""

import stat

import pytest

from src.core import config
from src.services import proton_account


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROTON_ACCOUNTS_FILE", str(tmp_path / "proton_accounts.json"))
    monkeypatch.setattr(config, "PROTON_ACCOUNTS_KEY_FILE", str(tmp_path / "proton_accounts.key"))
    return tmp_path


def test_round_trip(store):
    saved = proton_account.save("alice", "user@example.com", "secret", "GEZDGNBVGY3TQOJQ")
    assert saved.configured
    loaded = proton_account.load("alice")
    assert (loaded.username, loaded.password, loaded.totp) == (
        "user@example.com",
        "secret",
        "GEZDGNBVGY3TQOJQ",
    )
    assert (store / "proton_accounts.json").is_file()
    assert (store / "proton_accounts.key").is_file()


def test_profiles_are_independent(store):
    proton_account.save("alice", "alice@example.com", "alice-pass")
    proton_account.save("bob", "bob@example.com", "bob-pass")
    assert proton_account.load("alice").password == "alice-pass"
    assert proton_account.load("bob").password == "bob-pass"
    assert not proton_account.load("carol").configured


def test_password_is_not_plaintext_and_files_are_private(store):
    proton_account.save("alice", "user@example.com", "top-secret")
    raw = (store / "proton_accounts.json").read_text(encoding="utf-8")
    assert "top-secret" not in raw
    if hasattr(stat, "S_IMODE"):
        assert stat.S_IMODE((store / "proton_accounts.json").stat().st_mode) == 0o600
        assert stat.S_IMODE((store / "proton_accounts.key").stat().st_mode) == 0o600


def test_omitting_the_password_keeps_it_for_that_profile(store):
    proton_account.save("alice", "user@example.com", "secret")
    proton_account.save("alice", "other@example.com", None, "NEWSECRET")
    loaded = proton_account.load("alice")
    assert loaded.username == "other@example.com"
    assert loaded.password == "secret"
    assert loaded.totp == "NEWSECRET"


def test_public_never_returns_the_secrets(store):
    account = proton_account.save("alice", "user@example.com", "secret", "TOTP")
    assert account.public() == {
        "username": "user@example.com",
        "has_password": True,
        "totp_set": True,
    }


def test_rename_moves_the_entry(store):
    proton_account.save("alice", "user@example.com", "secret")
    proton_account.rename("alice", "alice-2")
    assert not proton_account.load("alice").configured
    assert proton_account.load("alice-2").password == "secret"


def test_clearing_one_profile_keeps_the_others(store):
    proton_account.save("alice", "alice@example.com", "one")
    proton_account.save("bob", "bob@example.com", "two")
    proton_account.clear("alice")
    assert not proton_account.load("alice").configured
    assert proton_account.load("bob").password == "two"
    assert (store / "proton_accounts.json").is_file()


def test_clearing_the_last_profile_removes_the_files(store):
    proton_account.save("alice", "alice@example.com", "one")
    proton_account.clear("alice")
    assert not (store / "proton_accounts.json").exists()
    assert not (store / "proton_accounts.key").exists()


def test_a_lost_key_asks_for_the_password_again(store):
    proton_account.save("alice", "user@example.com", "secret")
    (store / "proton_accounts.key").write_bytes(b"not-the-key")
    loaded = proton_account.load("alice")
    assert loaded.username == "user@example.com"
    assert loaded.password == ""
    assert not loaded.configured


def test_empty_username_clears_that_profile(store):
    proton_account.save("alice", "user@example.com", "secret")
    assert not proton_account.save("alice", "   ").configured
    assert not proton_account.load("alice").configured
