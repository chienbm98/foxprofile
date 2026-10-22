import base64
import json

import pytest
from fastapi.testclient import TestClient

from src.services.automation.engine import ActivityLog, Automation
from src.services.browser import login
from src.services.profile.manager import ProfileManager
from src.services.vault import vault
from src.services.vault.accounts import AccountVault


@pytest.fixture(autouse=True)
def _isolated_vault(monkeypatch):
    monkeypatch.setattr(vault, "_session_passphrase", None)
    monkeypatch.setattr(vault, "_keyring", lambda: None)
    for key in ("FOXPROFILE_VAULT_PASSPHRASE", "FOXPROFILE_SYNC_PASSPHRASE"):
        monkeypatch.delenv(key, raising=False)


def test_totp_matches_rfc6238_vector():
    secret = base64.b32encode(b"12345678901234567890").decode()
    assert vault.totp(secret, at=59, digits=8) == ("94287082", 1)
    assert vault.totp(" " + secret.lower() + " ", at=59, digits=8)[0] == "94287082"
    with pytest.raises(vault.VaultError):
        vault.totp("not base32!!")


def test_encrypt_roundtrip_wrong_passphrase_and_locked():
    token = vault.encrypt("hunter2", "pw")
    assert token.startswith("FPV1:") and "hunter2" not in token
    assert vault.decrypt(token, "pw") == "hunter2"
    with pytest.raises(vault.VaultError):
        vault.decrypt(token, "other")
    with pytest.raises(vault.VaultLocked):
        vault.encrypt("x")


def test_passphrase_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("FOXPROFILE_SYNC_PASSPHRASE", "from-env")
    assert vault.get_passphrase() == "from-env"
    assert vault.set_passphrase("session", persist=False) == "session"
    assert vault.get_passphrase() == "session"


def test_secrets_are_stored_encrypted_and_only_valid_tokens_load(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vault.set_passphrase("pw", persist=False)
    pm = ProfileManager()
    pm.add_profile("p", "", "linux")
    av = AccountVault(pm)
    flags = av.set_secrets("p", {"password": "S3cret!", "hint": "first pet"})
    assert flags["has_password"] and flags["has_hint"] and not flags["has_totp_secret"]
    assert av.reveal("p", "password") == "S3cret!"
    on_disk = (tmp_path / "profiles.json").read_text()
    assert "S3cret!" not in on_disk and "first pet" not in on_disk
    av.set_secrets("p", {"password": None})
    assert not av.flags("p")["has_password"]
    with pytest.raises(vault.VaultError):
        av.set_secrets("p", {"totp_secret": "!!not base32!!"})
    data = json.loads((tmp_path / "profiles.json").read_text())
    data["p"]["secrets"]["password"] = "plain text smuggled in"
    (tmp_path / "profiles.json").write_text(json.dumps(data))
    assert "password" not in ProfileManager().profiles["p"].secrets


def test_secrets_travel_in_the_profile_archive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vault.set_passphrase("pw", persist=False)
    pm = ProfileManager()
    pm.add_profile("p", "", "linux")
    AccountVault(pm).set_secrets("p", {"password": "abc"})
    ok, zip_path = pm.export_profile("p", str(tmp_path))
    pm.delete_profile("p")
    ok, name = pm.import_profile(zip_path)
    assert ok and AccountVault(pm).reveal(name, "password") == "abc"


def test_api_never_returns_secret_values_and_locks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from src.api.app import create_app
    from src.core.container import Container

    with TestClient(create_app(Container()), base_url="http://127.0.0.1:8000") as c:
        assert c.post("/api/v1/profiles", json={"name": "g1", "email": "a@b.co"}).status_code == 201
        assert c.get("/api/v1/vault").json() == {"unlocked": False}
        locked = c.put("/api/v1/profiles/g1/secrets", json={"password": "pw1"})
        assert locked.status_code == 423
        assert c.post(
            "/api/v1/vault/passphrase", json={"passphrase": "pp", "persist": False}
        ).json()["unlocked"]
        secret = base64.b32encode(b"12345678901234567890").decode()
        flags = c.put(
            "/api/v1/profiles/g1/secrets", json={"password": "pw1", "totp_secret": secret}
        ).json()
        assert flags["has_password"] and flags["has_totp_secret"]
        listed = c.get("/api/v1/profiles/g1").json()
        assert listed["has_password"] is True and "pw1" not in json.dumps(listed)
        assert c.get("/api/v1/profiles/g1/secrets/password").json()["value"] == "pw1"
        code = c.get("/api/v1/profiles/g1/totp").json()
        assert len(code["code"]) == 6 and 1 <= code["remaining"] <= 30
        assert c.get("/api/v1/profiles/g1/secrets/bogus").status_code == 400
        patched = c.patch(
            "/api/v1/profiles/g1", json={"auto_login": True, "login_mode": "email_only"}
        )
        assert patched.json()["auto_login"] is True and patched.json()["login_mode"] == "email_only"
        assert c.patch("/api/v1/profiles/g1", json={"login_mode": "nope"}).status_code == 400


# --- sign-in state machine against a scripted Google ------------------------------------


class FakeGoogle:
    """control() stand-in: pages advance when the right thing is typed and Enter pressed."""

    def __init__(self, pages, email="me@gmail.com", password="pw", totp=None):
        self.pages, self.email, self.password, self.totp = pages, email, password, totp
        self.i, self.typed, self.calls = 0, "", []

    def _page(self):
        step = self.pages[self.i]
        if step == "inbox":
            return {
                "step": "unknown",
                "url": "https://mail.google.com/mail/u/0/#inbox",
                "title": f"Inbox - {self.email} - Gmail",
                "accounts": [],
            }
        urls = {"chooser": "https://accounts.google.com/v3/signin/accountchooser"}
        return {
            "step": step,
            "url": urls.get(step, "https://accounts.google.com/v3/signin/identifier"),
            "title": "Sign in",
            "accounts": [self.email] if step == "chooser" else [],
        }

    def __call__(self, name, action, params=None, timeout=60):
        self.calls.append((action, params))
        if action == "evaluate":
            return {"result": self._page()}
        if action == "keyboard_type":
            self.typed += params["text"]
        if action == "press" and self.i < len(self.pages) - 1:
            step = self.pages[self.i]
            expected = {"email": self.email, "password": self.password, "totp": self.totp}.get(step)
            if expected is None or self.typed == expected:
                self.i += 1
            self.typed = ""
        if action == "click" and self.pages[self.i] == "chooser":
            self.i += 1
        return {}


def _run(g, **kw):
    kw.setdefault("totp_code", None)
    return login.sign_in(
        g, "p", "me@gmail.com", kw.pop("password", "pw"), sleep=lambda s: None, **kw
    )


def test_signs_in_with_email_and_password():
    g = FakeGoogle(["email", "password", "inbox"])
    assert _run(g)["state"] == "logged_in"
    assert "".join(p["text"] for a, p in g.calls if a == "keyboard_type") == "me@gmail.compw"


def test_signs_in_through_account_chooser_and_totp():
    g = FakeGoogle(["chooser", "password", "totp", "inbox"], totp="123456")
    assert _run(g, totp_code=lambda: "123456")["state"] == "logged_in"


def test_stops_when_2fa_is_needed_but_no_key_is_stored():
    g = FakeGoogle(["email", "password", "totp", "inbox"], totp="123456")
    result = _run(g)
    assert result["state"] == "needs_verification" and "2-step" in result["detail"]


def test_wrong_password_is_tried_once_not_in_a_loop():
    g = FakeGoogle(["email", "password", "password", "inbox"], password="right")
    result = _run(g, password="wrong")
    assert result["state"] == "needs_verification"
    typed = "".join(p["text"] for a, p in g.calls if a == "keyboard_type")
    assert typed == "me@gmail.comwrong"


def test_challenge_and_unknown_pages_stop():
    assert _run(FakeGoogle(["email", "challenge", "inbox"]))["state"] == "needs_verification"
    assert _run(FakeGoogle(["unknown"]))["state"] == "needs_verification"


def test_modes_and_missing_credentials_never_touch_the_page():
    g = FakeGoogle(["email", "inbox"])
    assert login.sign_in(g, "p", "me@gmail.com", "pw", None, mode="manual")["state"] == "failed"
    assert login.sign_in(g, "p", "", "pw", None)["state"] == "failed"
    assert login.sign_in(g, "p", "me@gmail.com", None, None)["state"] == "failed"
    assert g.calls == []
    half = FakeGoogle(["email", "password", "inbox"])
    assert (
        login.sign_in(
            half, "p", "me@gmail.com", None, None, mode="email_only", sleep=lambda s: None
        )["state"]
        == "needs_verification"
    )
    assert "".join(p["text"] for a, p in half.calls if a == "keyboard_type") == "me@gmail.com"


# --- wiring: session check -> automatic re-login --------------------------------------------


class _Launcher:
    def __init__(self, google):
        self.google, self.running = google, set()

    def is_running(self, n):
        return n in self.running

    def start_thread(self, profile, log, **kw):
        return True

    def wait_for_launch(self, n, t):
        self.running.add(n)
        return True, None

    def stop_profile(self, n, timeout=2):
        self.running.discard(n)

    def control(self, n, action, params=None, timeout=60):
        return self.google(n, action, params)


def _automation(tmp_path, monkeypatch, pages, **profile):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("src.services.browser.session_check.time.sleep", lambda s: None)
    monkeypatch.setattr("src.services.browser.login.time.sleep", lambda s: None)
    monkeypatch.setattr("src.services.browser.login.random.uniform", lambda a, b: 0)
    vault.set_passphrase("pw", persist=False)
    pm = ProfileManager()
    pm.add_profile("p", "", "linux")
    pm.update_meta("p", email="me@gmail.com", **profile)
    av = AccountVault(pm)
    av.set_secrets("p", {"password": "pw"})
    google = FakeGoogle(pages)
    auto = Automation(
        pm,
        _Launcher(google),
        vault=av,
        path=str(tmp_path / "a.json"),
        log=ActivityLog(str(tmp_path / "log")),
    )
    return auto, pm, google


def test_session_check_signs_back_in_when_auto_login_is_on(tmp_path, monkeypatch):
    # Gmail first sends the profile to the sign-in page, then accepts the credentials.
    class Flow(FakeGoogle):
        def __init__(self):
            super().__init__(["email", "password", "inbox"])
            self.visits = 0

        def _page(self):
            if self.pages[self.i] == "email" and self.visits == 0 and not self.typed:
                self.visits += 1
                return {
                    "step": "unknown",
                    "url": "https://accounts.google.com/x",
                    "title": "",
                    "accounts": [],
                }
            return super()._page()

    auto, pm, _ = _automation(
        tmp_path, monkeypatch, ["email", "password", "inbox"], auto_login=True
    )
    auto.launcher.google = Flow()
    result = auto.check_session("p")
    assert result["state"] == "alive"
    assert pm.profiles["p"].session_state == "alive"
    events = [e["event"] for e in auto.log.tail()]
    assert "relogin" in events
    log_text = (tmp_path / "log").read_text()
    assert "pw" not in log_text.replace("password", "").replace("passw", "")


def test_automatic_relogin_waits_out_the_cooldown_but_the_button_does_not(tmp_path, monkeypatch):
    auto, pm, google = _automation(
        tmp_path, monkeypatch, ["email", "password", "password"], auto_login=True
    )
    auto.launcher.running.add("p")
    first = auto._relogin_running("p", manual=False)
    assert first["state"] == "needs_verification"
    assert pm.profiles["p"].session_state == "needs_verification"
    assert auto._relogin_running("p", manual=False) is None
    google.i, google.typed = 0, ""
    assert auto._relogin_running("p", manual=True) is not None
