import pytest
from fastapi.testclient import TestClient

from src.services.profile import bundle
from src.services.profile.manager import ProfileManager
from src.services.vault import vault


@pytest.fixture(autouse=True)
def _vault(monkeypatch):
    monkeypatch.setattr(vault, "_session_passphrase", None)
    monkeypatch.setattr(vault, "_keyring", lambda: None)
    for key in ("FOXPROFILE_VAULT_PASSPHRASE", "FOXPROFILE_SYNC_PASSPHRASE"):
        monkeypatch.delenv(key, raising=False)


def _pm(root, monkeypatch):
    root.mkdir(exist_ok=True)
    monkeypatch.chdir(root)
    return ProfileManager()


def test_bundle_moves_profiles_with_logins_and_labels(tmp_path, monkeypatch):
    pm = _pm(tmp_path / "A", monkeypatch)
    for name in ("g1", "g2"):
        pm.add_profile(name, "", "windows")
        (tmp_path / "A" / "camoufox_data" / name / "cookies.sqlite").write_bytes(name.encode())
    pm.update_meta("g1", email="a@b.co", tags=["gmail"])
    out = str(tmp_path / "p.fpbundle")
    result = bundle.export_bundle(pm, None, "pw", out)
    assert sorted(result["profiles"]) == ["g1", "g2"]
    with open(out, "rb") as f:
        assert b"cookies" not in f.read()

    pm2 = _pm(tmp_path / "B", monkeypatch)
    got = bundle.import_bundle(pm2, out, "pw")
    assert sorted(got["imported"]) == ["g1", "g2"] and not got["skipped"]
    assert (tmp_path / "B" / "camoufox_data" / "g1" / "cookies.sqlite").read_bytes() == b"g1"
    assert pm2.profiles["g1"].email == "a@b.co" and pm2.profiles["g1"].tags == ["gmail"]


def test_wrong_passphrase_existing_names_and_running(tmp_path, monkeypatch):
    pm = _pm(tmp_path / "A", monkeypatch)
    pm.add_profile("g1", "", "linux")
    pm.add_profile("g2", "", "linux")
    out = str(tmp_path / "p.fpbundle")
    result = bundle.export_bundle(pm, None, "pw", out, is_running=lambda n: n == "g2")
    assert result["profiles"] == ["g1"] and "g2" in result["skipped"]
    with pytest.raises(bundle.BundleError):
        bundle.import_bundle(pm, out, "wrong")
    again = bundle.import_bundle(pm, out, "pw")
    assert again["imported"] == [] and "already exists" in again["skipped"]["g1"]
    (tmp_path / "A" / "camoufox_data" / "g1" / "stale.txt").write_text("old")
    forced = bundle.import_bundle(pm, out, "pw", overwrite=True)
    assert forced["imported"] == ["g1"]
    assert not (tmp_path / "A" / "camoufox_data" / "g1" / "stale.txt").exists()
    with pytest.raises(bundle.BundleError, match="Nothing to export"):
        bundle.export_bundle(pm, ["g1"], "pw", out, is_running=lambda n: True)


def test_api_download_then_upload(tmp_path, monkeypatch):
    from src.api.app import create_app
    from src.core.container import Container

    _pm(tmp_path / "A", monkeypatch)
    with TestClient(create_app(Container()), base_url="http://127.0.0.1:8000") as c:
        c.post("/api/v1/profiles", json={"name": "g1", "email": "a@b.co"})
        assert c.post("/api/v1/transfer/export", json={}).status_code == 423
        vault.set_passphrase("pp", persist=False)
        r = c.post("/api/v1/transfer/export", json={"names": ["g1"]})
        assert r.status_code == 200 and ".fpbundle" in r.headers["content-disposition"]
        blob = r.content
        assert c.post("/api/v1/transfer/import", content=blob).json()["skipped"]["g1"]
        done = c.post("/api/v1/transfer/import?overwrite=true", content=blob).json()
        assert done["imported"] == ["g1"]
        assert c.post("/api/v1/transfer/import", content=b"junk" * 50).status_code == 400
        bad = c.post("/api/v1/transfer/import", content=blob, headers={"x-bundle-passphrase": "no"})
        assert bad.status_code == 400
