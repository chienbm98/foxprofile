"""The Proton account store never loses or exposes secrets silently."""

import json

import pytest

from src.core import config
from src.core.errors import ProtonStoreError
from src.services import proton_account


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROTON_ACCOUNTS_FILE", str(tmp_path / "proton_accounts.json"))
    monkeypatch.setattr(config, "PROTON_ACCOUNTS_KEY_FILE", str(tmp_path / "proton_accounts.key"))
    return tmp_path


def test_totp_is_encrypted_at_rest(store):
    proton_account.save("alice", "user@example.com", "secret", "GEZDGNBVGY3TQOJQ")
    raw = (store / "proton_accounts.json").read_text(encoding="utf-8")
    assert "GEZDGNBVGY3TQOJQ" not in raw
    assert proton_account.load("alice").totp == "GEZDGNBVGY3TQOJQ"


def test_a_corrupt_key_is_never_replaced(store):
    proton_account.save("alice", "user@example.com", "secret")
    key_file = store / "proton_accounts.key"
    key_file.write_bytes(b"not-the-key")
    accounts_before = (store / "proton_accounts.json").read_bytes()

    with pytest.raises(ProtonStoreError):
        proton_account.save("bob", "bob@example.com", "bob-pass")
    assert key_file.read_bytes() == b"not-the-key"
    assert (store / "proton_accounts.json").read_bytes() == accounts_before


def test_a_corrupt_accounts_file_is_never_overwritten(store):
    accounts = store / "proton_accounts.json"
    accounts.write_text("{not json", encoding="utf-8")

    with pytest.raises(ProtonStoreError):
        proton_account.save("alice", "user@example.com", "secret")
    assert accounts.read_text(encoding="utf-8") == "{not json"
    # Reads degrade to "no account" rather than failing the profile list.
    assert not proton_account.load("alice").configured


def test_ciphertext_survives_a_username_change_while_the_key_is_unreadable(store):
    proton_account.save("alice", "user@example.com", "secret", "GEZDGNBVGY3TQOJQ")
    key_file = store / "proton_accounts.key"
    good_key = key_file.read_bytes()
    key_file.write_bytes(b"lost")

    proton_account.save("alice", "new@example.com")  # username only: nothing is re-encrypted
    key_file.write_bytes(good_key)
    loaded = proton_account.load("alice")
    assert (loaded.username, loaded.password, loaded.totp) == (
        "new@example.com",
        "secret",
        "GEZDGNBVGY3TQOJQ",
    )


def test_a_plain_text_totp_from_older_versions_is_encrypted_on_next_save(store):
    accounts = store / "proton_accounts.json"
    proton_account.save("alice", "user@example.com", "secret")
    # Older versions stored the TOTP secret in plain text next to the encrypted password.
    data = json.loads(accounts.read_text(encoding="utf-8"))
    data["profiles"]["alice"]["totp"] = "GEZDGNBVGY3TQOJQ"
    accounts.write_text(json.dumps(data), encoding="utf-8")

    assert proton_account.load("alice").totp == "GEZDGNBVGY3TQOJQ"
    proton_account.save("alice", "user@example.com")  # any save migrates it
    raw = accounts.read_text(encoding="utf-8")
    assert "GEZDGNBVGY3TQOJQ" not in raw
    assert proton_account.load("alice").totp == "GEZDGNBVGY3TQOJQ"


def test_load_all_reads_the_key_once_for_every_account(store, monkeypatch):
    proton_account.save("alice", "alice@example.com", "one")
    proton_account.save("bob", "bob@example.com", "two")
    key_reads = []
    real_read_key = proton_account._read_key

    def counting_read_key():
        key_reads.append(1)
        return real_read_key()

    monkeypatch.setattr(proton_account, "_read_key", counting_read_key)
    accounts = proton_account.load_all()
    assert {name: account.password for name, account in accounts.items()} == {
        "alice": "one",
        "bob": "two",
    }
    assert len(key_reads) == 1


def test_load_all_of_an_empty_store(store):
    assert proton_account.load_all() == {}
