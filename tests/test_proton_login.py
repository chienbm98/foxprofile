"""The Proton sign-in helper: TOTP, account gating and the success marker."""

import asyncio
import json
import time

import pytest

from src.core import config
from src.services.browser import proton_login
from src.services.proton_account import ProtonAccount

SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # base32 of "12345678901234567890"


def _account(monkeypatch, account: ProtonAccount) -> None:
    monkeypatch.setattr(proton_login.proton_account, "load", lambda profile: account)


@pytest.mark.parametrize(
    ("at", "digits", "expected"),
    [(59, 6, "287082"), (59, 8, "94287082"), (1_111_111_109, 8, "07081804")],
)
def test_totp_matches_rfc6238(at, digits, expected):
    assert proton_login.totp(SECRET, at=at, digits=digits) == expected


def test_totp_accepts_spaces_and_an_otpauth_uri():
    spaced = "GEZD GNBV GY3T QOJQ GEZD GNBV GY3T QOJQ"
    assert proton_login.totp(spaced, at=59) == "287082"
    uri = f"otpauth://totp/Proton:user?secret={SECRET}&issuer=Proton"
    assert proton_login.totp(uri, at=59) == "287082"


def test_configured_comes_from_the_saved_account(monkeypatch):
    _account(monkeypatch, ProtonAccount())
    assert not proton_login.configured("alice")
    _account(monkeypatch, ProtonAccount("user@example.com", "secret"))
    assert proton_login.configured("alice")


def test_success_marker_respects_the_day_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROTON_LOGIN_DAYS", 7)
    proton_login._remember(tmp_path)
    assert proton_login.logged_in_recently(tmp_path)

    monkeypatch.setattr(config, "PROTON_LOGIN_DAYS", 0)
    assert not proton_login.logged_in_recently(tmp_path)

    (tmp_path / proton_login.MARKER).write_text(
        json.dumps({"at": int(time.time() - 8 * 86_400)}), encoding="utf-8"
    )
    monkeypatch.setattr(config, "PROTON_LOGIN_DAYS", 7)
    assert not proton_login.logged_in_recently(tmp_path)


def test_auto_login_is_a_no_op_without_an_account(tmp_path, monkeypatch):
    _account(monkeypatch, ProtonAccount())
    logs = []
    assert (
        asyncio.run(proton_login.auto_login(None, tmp_path, "chrome", "alice", log=logs.append))
        is False
    )
    assert logs == []


def test_camoufox_login_needs_a_marionette_port(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROTON_LOGIN_DAYS", 7)
    _account(monkeypatch, ProtonAccount("user@example.com", "secret"))
    events = []
    logs = []

    class FakeContext:
        pages = []

        def on(self, event, handler):
            events.append((event, handler))

    # Camoufox is driven through Marionette: without a port there is nothing to drive.
    result = asyncio.run(
        proton_login.auto_login(FakeContext(), tmp_path, "camoufox", "alice", log=logs.append)
    )
    assert result is False
    assert events == []
    assert "without a Marionette port" in logs[-1]


def test_camoufox_login_runs_over_marionette(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROTON_LOGIN_DAYS", 7)
    _account(monkeypatch, ProtonAccount("user@example.com", "secret"))
    calls = []

    async def fake_login(context, profile_dir, account, *, marionette_port, log, country):
        calls.append((marionette_port, country, account.username))
        return True

    monkeypatch.setattr(proton_login, "_camoufox_auto_login", fake_login)
    result = asyncio.run(
        proton_login.auto_login(
            object(),
            tmp_path,
            "camoufox",
            "alice",
            log=lambda _message: None,
            country="US",
            marionette_port=4444,
        )
    )
    assert result is True
    assert calls == [(4444, "US", "user@example.com")]
