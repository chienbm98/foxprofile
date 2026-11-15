"""A launch never advertises the machine's own address over WebRTC, and keeps Marionette on Proton."""

import asyncio

import pytest

from src.core import config
from src.services import proton_account
from src.services.browser import runner


@pytest.fixture
def launch(monkeypatch, tmp_path):
    """Run one launch up to the browser start; return the config Camoufox would have got."""
    seen = {}

    def capture(**kwargs):
        seen.update(kwargs)
        raise RuntimeError("stop before the browser")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner, "HEADLESS", True)
    monkeypatch.setattr(runner, "AsyncCamoufox", capture)
    monkeypatch.setattr(runner, "load_or_create", lambda *_: {})
    monkeypatch.setattr(runner, "exit_ip", lambda *_: "198.51.100.5")
    monkeypatch.setattr(runner, "stable_locale", lambda *_: "en-US")
    monkeypatch.setattr(runner.extensions, "install_firefox", lambda *_: ["Proton VPN 1.3.7"])
    monkeypatch.setattr(config, "PROTON_ACCOUNTS_FILE", str(tmp_path / "proton_accounts.json"))
    monkeypatch.setattr(config, "PROTON_ACCOUNTS_KEY_FILE", str(tmp_path / "proton_accounts.key"))
    proton_account.save("p", "user@example.com", "secret")

    def run(proxy: str, extension: str = ""):
        asyncio.run(runner.run_browser("p", proxy, "windows", "", "", extension))
        return seen

    return run


def test_a_proton_profile_gives_no_real_address_to_webrtc(launch):
    used = launch("None", "proton-vpn")
    prefs = used["firefox_user_prefs"]
    # Camoufox would otherwise spoof the address from before the VPN into WebRTC.
    assert used["geoip"] is False
    assert prefs["media.peerconnection.ice.proxy_only"] is True
    assert prefs["media.peerconnection.ice.no_host"] is True
    assert prefs["media.peerconnection.ice.default_address_only"] is True
    # The WebRTC prefs are merged with the Marionette prefs, not replaced by them.
    assert prefs["marionette.enabled"] is True


def test_a_proxied_profile_keeps_webrtc_behind_the_proxy(launch):
    used = launch("socks5://192.0.2.1:1080")
    assert used["geoip"] == "198.51.100.5"
    assert used["firefox_user_prefs"]["media.peerconnection.ice.proxy_only"] is True


def test_a_direct_profile_reports_its_address_as_before(launch):
    used = launch("None")
    assert used["geoip"] == "198.51.100.5"
    prefs = used["firefox_user_prefs"]
    assert prefs["media.peerconnection.ice.no_host"] is True
    assert "media.peerconnection.ice.proxy_only" not in prefs
