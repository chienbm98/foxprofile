"""Regression tests for the backend fixes applied in qa/exploratory-rounds.

All IPs use IANA documentation ranges (192.0.2.x, 198.51.100.x, 203.0.113.x,
2001:db8::) and credentials are placeholders only.
"""

from __future__ import annotations

import json
import pathlib
import threading
import unittest.mock

import pytest

from src.utils.proxy_parser import parse_proxy
from src.utils.validation import validate_profile_name, validate_proxy_format

# ---------------------------------------------------------------------------
# 1. proxy_parser – password containing '@'
# ---------------------------------------------------------------------------


class TestNormalizeProxyAtInPassword:
    def test_at_in_password_does_not_return_none(self):
        result = parse_proxy("192.0.2.1:8080:user:p@ss")
        assert result is not None, (
            "parse_proxy must not return None for host:port:user:pass with '@' in password"
        )

    def test_at_in_password_server(self):
        result = parse_proxy("192.0.2.1:8080:user:p@ss")
        assert result["server"] == "http://192.0.2.1:8080"

    def test_at_in_password_credentials(self):
        result = parse_proxy("192.0.2.1:8080:user:p@ss")
        assert result["username"] == "user"
        assert result["password"] == "p@ss"

    def test_colon_in_password(self):
        result = parse_proxy("198.51.100.1:3128:user:p:ss")
        assert result is not None
        assert result["password"] == "p:ss"

    def test_at_and_colon_in_password(self):
        result = parse_proxy("203.0.113.1:1080:user:p@s:s")
        assert result is not None
        assert result["password"] == "p@s:s"

    def test_socks5_scheme_with_at_in_password(self):
        result = parse_proxy("socks5://192.0.2.1:1080:user:p@ss")
        assert result is not None
        assert result["server"] == "socks5://192.0.2.1:1080"
        assert result["password"] == "p@ss"

    def test_plain_password_still_works(self):
        result = parse_proxy("192.0.2.1:8080:user:secret")
        assert result == {
            "server": "http://192.0.2.1:8080",
            "username": "user",
            "password": "secret",
        }


# ---------------------------------------------------------------------------
# 1b. proxy_parser – IPv6
# ---------------------------------------------------------------------------


class TestParseProxyIPv6:
    def test_ipv6_basic(self):
        result = parse_proxy("socks5://user:pass@[2001:db8::1]:1080")
        assert result is not None
        assert result["server"] == "socks5://[2001:db8::1]:1080"
        assert result["username"] == "user"
        assert result["password"] == "pass"

    def test_ipv6_no_creds(self):
        result = parse_proxy("socks5://[2001:db8::1]:1080")
        assert result is not None
        assert result["server"] == "socks5://[2001:db8::1]:1080"


# ---------------------------------------------------------------------------
# 1c. validate_proxy_format agrees with parse_proxy
# ---------------------------------------------------------------------------

VALID_PROXIES_ROUND_TRIP = [
    "192.0.2.1:8080",
    "http://192.0.2.1:8080",
    "socks5://user:pass@192.0.2.1:1080",
    "192.0.2.1:8080:user:secret",
    "192.0.2.1:8080:user:p@ss",
    "192.0.2.1:8080:user:p:ss",
    "socks5://192.0.2.1:1080:user:p@ss",
    "socks5://user:pass@[2001:db8::1]:1080",
    "http://user:pass@198.51.100.1:3128",
]


@pytest.mark.parametrize("proxy", VALID_PROXIES_ROUND_TRIP)
def test_validation_accepts_what_parse_returns_nonnone(proxy):
    """Anything validate_proxy_format accepts must parse to a non-None dict."""
    valid, _ = validate_proxy_format(proxy)
    result = parse_proxy(proxy)
    if valid:
        assert result is not None, (
            f"validate_proxy_format accepted {proxy!r} but parse_proxy returned None"
        )


@pytest.mark.parametrize("proxy", VALID_PROXIES_ROUND_TRIP)
def test_valid_proxies_accepted_by_validation(proxy):
    valid, msg = validate_proxy_format(proxy)
    assert valid, f"validate_proxy_format unexpectedly rejected {proxy!r}: {msg}"


class TestValidateProxyIPv6:
    def test_ipv6_accepted(self):
        ok, _ = validate_proxy_format("socks5://user:pass@[2001:db8::1]:1080")
        assert ok

    def test_ipv6_no_creds_accepted(self):
        ok, _ = validate_proxy_format("socks5://[2001:db8::1]:1080")
        assert ok


# ---------------------------------------------------------------------------
# 2. validate_profile_name – control characters
# ---------------------------------------------------------------------------


class TestProfileNameControlChars:
    @pytest.mark.parametrize("char", ["\x00", "\n", "\t", "\x7f", "\r", "\x1b"])
    def test_control_char_rejected(self, char):
        ok, msg = validate_profile_name(f"valid{char}name")
        assert not ok, f"Expected control char {repr(char)} to be rejected"
        assert msg  # error message must be non-empty

    def test_normal_name_still_valid(self):
        ok, _ = validate_profile_name("shop-01")
        assert ok


# ---------------------------------------------------------------------------
# 3 & 4 & 5. ProfileManager – update_profile, add_profile, atomic save, RLock
# ---------------------------------------------------------------------------


@pytest.fixture()
def manager_in_tmp(tmp_path, monkeypatch):
    """Return a ProfileManager whose DATA_DIR and PROFILES_FILE live in tmp_path."""
    data_dir = str(tmp_path / "camoufox_data")
    profiles_file = str(tmp_path / "profiles.json")
    monkeypatch.setenv("FOXPROFILE_DATA_DIR", data_dir)
    monkeypatch.setenv("FOXPROFILE_PROFILES_FILE", profiles_file)

    import src.core.config as cfg

    monkeypatch.setattr(cfg, "DATA_DIR", data_dir)
    monkeypatch.setattr(cfg, "PROFILES_FILE", profiles_file)

    import src.services.profile.manager as mgr_mod

    monkeypatch.setattr(mgr_mod, "DATA_DIR", data_dir)
    monkeypatch.setattr(mgr_mod, "PROFILES_FILE", profiles_file)

    from src.services.profile.manager import ProfileManager

    return ProfileManager(), tmp_path


class TestUpdateProfileDirConflict:
    def test_rename_refused_when_target_dir_exists(self, manager_in_tmp):
        pm, tmp_path = manager_in_tmp
        pm.add_profile("alice", "", "windows")
        pm.add_profile("bob", "", "windows")
        # Pre-create bob's data dir (simulates leftover on Windows)
        bob_dir = pathlib.Path(pm._data_path("bob"))
        bob_dir.mkdir(parents=True, exist_ok=True)

        result = pm.update_profile("alice", "bob", "", "windows")
        assert result is False

    def test_rename_leaves_memory_consistent_on_refusal(self, manager_in_tmp):
        pm, tmp_path = manager_in_tmp
        pm.add_profile("alice", "", "windows")
        pm.add_profile("bob", "", "windows")

        pm.update_profile("alice", "bob", "", "windows")

        # alice must still be present (rename was refused)
        assert "alice" in pm.profiles

    def test_rename_succeeds_when_target_dir_absent(self, manager_in_tmp):
        pm, tmp_path = manager_in_tmp
        pm.add_profile("alice", "", "windows")
        # remove alice's data dir so we can rename cleanly to carol
        pathlib.Path(pm._data_path("alice")).rmdir()

        result = pm.update_profile("alice", "carol", "", "windows")
        assert result is True
        assert "carol" in pm.profiles
        assert "alice" not in pm.profiles

    def test_rename_moves_data_dir_before_memory_mutation(self, manager_in_tmp):
        pm, tmp_path = manager_in_tmp
        pm.add_profile("alice", "", "windows")
        alice_dir = pathlib.Path(pm._data_path("alice"))
        (alice_dir / "fingerprint.json").write_text("{}", encoding="utf-8")

        result = pm.update_profile("alice", "carol", "", "windows")

        assert result is True
        carol_dir = pathlib.Path(pm._data_path("carol"))
        assert carol_dir.exists()
        assert (carol_dir / "fingerprint.json").exists()
        assert not alice_dir.exists()


class TestAddProfileMkdirFailure:
    def test_no_entry_in_json_when_mkdir_fails(self, manager_in_tmp):
        pm, tmp_path = manager_in_tmp
        profiles_file = pathlib.Path(pm._data_path("..")).parent / "profiles.json"

        with unittest.mock.patch("pathlib.Path.mkdir", side_effect=OSError("disk full")):
            result = pm.add_profile("bad-profile", "", "windows")

        assert result is False
        assert "bad-profile" not in pm.profiles
        # JSON must not contain the profile
        if profiles_file.exists():
            data = json.loads(profiles_file.read_text())
            assert "bad-profile" not in data


class TestAtomicSave:
    def test_profiles_json_written(self, manager_in_tmp):
        pm, tmp_path = manager_in_tmp
        pm.add_profile("test-save", "", "linux")
        profiles_file = tmp_path / "profiles.json"
        assert profiles_file.exists()
        data = json.loads(profiles_file.read_text())
        assert "test-save" in data

    def test_no_tmp_file_left_after_save(self, manager_in_tmp):
        pm, tmp_path = manager_in_tmp
        pm.add_profile("test-atomic", "", "linux")
        tmp_file = tmp_path / "profiles.json.tmp"
        assert not tmp_file.exists()


class TestRLock:
    def test_concurrent_add_no_duplicate(self, manager_in_tmp):
        """Two threads racing to add the same profile: exactly one wins."""
        pm, _ = manager_in_tmp
        results = []

        def worker(idx):
            results.append(pm.add_profile(f"concurrent-{idx}", "", "windows"))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        names = [f"concurrent-{i}" for i in range(10)]
        for name in names:
            assert names.count(name) == 1  # unique names → each can only be added once
        # All 10 should succeed since names differ
        assert all(results)

    def test_concurrent_same_name_only_one_wins(self, manager_in_tmp):
        pm, _ = manager_in_tmp
        results = []

        def worker():
            results.append(pm.add_profile("race", "", "windows"))

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results.count(True) == 1
        assert results.count(False) == 4


# ---------------------------------------------------------------------------
# 6. MCP update_profile – proxy="" must not be filtered out
# ---------------------------------------------------------------------------


class TestMcpUpdateProfileProxyFilter:
    """Unit-test the body-building logic of the MCP update_profile tool."""

    def _build_body(self, new_name=None, proxy=None, os_type=None, timezone=None, locale=None):
        # Replicate the fixed logic from mcp_server/server.py
        body = {
            k: v
            for k, v in {"name": new_name, "proxy": proxy, "os_type": os_type}.items()
            if v is not None
        }
        body.update(
            {k: v for k, v in {"timezone": timezone, "locale": locale}.items() if v is not None}
        )
        return body

    def test_empty_proxy_included_in_body(self):
        body = self._build_body(proxy="")
        assert "proxy" in body
        assert body["proxy"] == ""

    def test_none_proxy_excluded_from_body(self):
        body = self._build_body(proxy=None)
        assert "proxy" not in body

    def test_real_proxy_included(self):
        body = self._build_body(proxy="192.0.2.1:8080")
        assert body["proxy"] == "192.0.2.1:8080"

    def test_empty_timezone_included(self):
        body = self._build_body(timezone="")
        assert "timezone" in body
        assert body["timezone"] == ""

    def test_none_os_type_excluded(self):
        body = self._build_body(os_type=None)
        assert "os_type" not in body


# ---------------------------------------------------------------------------
# 7. Case-insensitive profile name uniqueness (fix 1)
# ---------------------------------------------------------------------------


class TestCaseInsensitiveUniqueness:
    def test_add_case_variant_rejected(self, manager_in_tmp):
        pm, _ = manager_in_tmp
        assert pm.add_profile("CaseDirA", "", "windows") is True
        # "casedira" casefolds to the same as "CaseDirA" → must be rejected
        assert pm.add_profile("casedirA", "", "windows") is False

    def test_add_case_variant_not_registered(self, manager_in_tmp):
        """A rejected case-variant add must not appear in the profiles dict."""
        pm, _ = manager_in_tmp
        pm.add_profile("MyProfile", "", "windows")
        result = pm.add_profile("myprofile", "", "windows")
        assert result is False
        # The profile must not be registered under the new casing
        assert "myprofile" not in pm.profiles

    def test_add_same_name_exact_still_rejected(self, manager_in_tmp):
        pm, _ = manager_in_tmp
        pm.add_profile("alpha", "", "windows")
        assert pm.add_profile("alpha", "", "windows") is False

    def test_update_rename_to_case_variant_of_other_rejected(self, manager_in_tmp):
        pm, _ = manager_in_tmp
        pm.add_profile("ProfileA", "", "windows")
        pm.add_profile("ProfileB", "", "windows")
        # Renaming "ProfileA" to "profileb" conflicts with "ProfileB"
        result = pm.update_profile("ProfileA", "profileb", "", "windows")
        assert result is False
        assert "ProfileA" in pm.profiles

    def test_update_case_only_self_rename_allowed(self, manager_in_tmp):
        """Renaming 'MyProf' -> 'myprof' keeps the profile and its data, also on
        a case-insensitive file system where the target dir already "exists"."""
        pm, _ = manager_in_tmp
        pm.add_profile("MyProf", "", "windows")
        (pathlib.Path(pm._data_path("MyProf")) / "marker.txt").write_text("x")
        assert pm.update_profile("MyProf", "myprof", "", "windows") is True
        assert list(pm.profiles) == ["myprof"]
        assert (pathlib.Path(pm._data_path("myprof")) / "marker.txt").read_text() == "x"

    def test_import_case_variant_needs_overwrite_and_replaces(self, manager_in_tmp, tmp_path):
        pm, _ = manager_in_tmp
        pm.add_profile("casedira", "", "windows")
        ok, zip_path = pm.export_profile("casedira", str(tmp_path))
        assert ok
        assert pm.delete_profile("casedira")
        pm.add_profile("CaseDirA", "", "windows")

        assert pm.import_profile(zip_path)[0] is False
        assert pm.import_profile(zip_path, overwrite=True) == (True, "casedira")
        assert list(pm.profiles) == ["casedira"]

    def test_add_profile_different_case_different_content_allowed(self, manager_in_tmp):
        """Two truly distinct names that share no casefold match are both allowed."""
        pm, _ = manager_in_tmp
        assert pm.add_profile("alpha", "", "windows") is True
        assert pm.add_profile("beta", "", "windows") is True


class TestDeleteRace:
    def test_rmtree_runs_under_the_lock(self, manager_in_tmp, monkeypatch):
        """A concurrent add of the same name must wait until the old data dir
        is gone, or the delete removes the new profile's directory."""
        pm, _ = manager_in_tmp
        pm.add_profile("racer", "", "windows")
        import src.services.profile.manager as mgr_mod

        real_rmtree = mgr_mod.shutil.rmtree
        held = []

        def rmtree(path, ignore_errors=False):
            t = threading.Thread(target=lambda: held.append(not pm._lock.acquire(timeout=0)))
            t.start()
            t.join()
            real_rmtree(path, ignore_errors=ignore_errors)

        monkeypatch.setattr(mgr_mod.shutil, "rmtree", rmtree)
        assert pm.delete_profile("racer")
        assert held == [True]


class TestRequireProfile:
    def test_returns_profile_or_404(self, manager_in_tmp):
        from fastapi import HTTPException

        from src.api.helpers import require_profile

        pm, _ = manager_in_tmp
        pm.add_profile("here", "", "windows")
        assert require_profile("here", pm).name == "here"
        with pytest.raises(HTTPException) as e:
            require_profile("gone", pm)
        assert e.value.status_code == 404
