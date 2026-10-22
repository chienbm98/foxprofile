import io

import pytest

from src.services.profile.manager import ProfileManager
from src.services.sync.backends import FolderBackend, SyncError, open_backend
from src.services.sync.crypto import DecryptError, decrypt_stream, encrypt_stream
from src.services.sync.service import SyncConflict, SyncService


class _Idle:
    def __init__(self):
        self.running = set()

    def is_running(self, name):
        return name in self.running


def _enc(data, pw="pw"):
    out = io.BytesIO()
    encrypt_stream(io.BytesIO(data), out, pw)
    return out.getvalue()


def _dec(blob, pw="pw"):
    out = io.BytesIO()
    decrypt_stream(io.BytesIO(blob), out, pw)
    return out.getvalue()


def test_crypto_roundtrip_multi_chunk(monkeypatch):
    monkeypatch.setattr("src.services.sync.crypto.CHUNK", 1000)
    data = bytes(range(256)) * 20
    assert _dec(_enc(data)) == data
    assert _dec(_enc(b"")) == b""


def test_crypto_wrong_passphrase_and_truncation(monkeypatch):
    monkeypatch.setattr("src.services.sync.crypto.CHUNK", 1000)
    blob = _enc(b"x" * 5000)
    with pytest.raises(DecryptError):
        _dec(blob, "other")
    with pytest.raises(DecryptError):
        _dec(blob[: len(blob) - 1100])
    with pytest.raises(DecryptError):
        _dec(b"nope")


def test_open_backend_schemes(tmp_path):
    assert isinstance(open_backend(str(tmp_path / "s")), FolderBackend)
    with pytest.raises(SyncError):
        open_backend("ftp://x/y")
    with pytest.raises(SyncError):
        open_backend("")


def _machine(root, monkeypatch, store):
    root.mkdir(exist_ok=True)
    monkeypatch.chdir(root)
    pm = ProfileManager()
    launcher = _Idle()
    svc = SyncService(
        pm,
        launcher,
        backend=FolderBackend(str(store)),
        passphrase="secret",
        state_file=str(root / "sync_state.json"),
        data_dir="camoufox_data",
    )
    return pm, launcher, svc


def test_login_travels_between_machines(tmp_path, monkeypatch):
    store = tmp_path / "store"
    a = tmp_path / "A"
    b = tmp_path / "B"

    pm, _, svc = _machine(a, monkeypatch, store)
    pm.add_profile("gmail-1", "", "windows")
    d = a / "camoufox_data" / "gmail-1"
    (d / "cookies.sqlite").write_bytes(b"session-cookie")
    (d / "fingerprint.json").write_text('{"os":"windows","fingerprint":{}}')
    (d / "cache2").mkdir()
    (d / "cache2" / "junk").write_bytes(b"x" * 100)
    meta = svc.push("gmail-1")
    assert meta["version"] == 1
    raw = (store / "gmail-1.fpx").read_bytes()
    assert b"session-cookie" not in raw

    pm2, _, svc2 = _machine(b, monkeypatch, store)
    assert [r["state"] for r in svc2.status()] == ["remote-only"]
    svc2.pull("gmail-1")
    got = b / "camoufox_data" / "gmail-1"
    assert (got / "cookies.sqlite").read_bytes() == b"session-cookie"
    assert (got / "fingerprint.json").exists()
    assert not (got / "cache2").exists()
    assert "gmail-1" in pm2.profiles
    assert svc2.pull("gmail-1")["skipped"]


def test_conflict_and_force(tmp_path, monkeypatch):
    store = tmp_path / "store"
    pm, _, svc = _machine(tmp_path / "A", monkeypatch, store)
    pm.add_profile("p", "", "linux")
    svc.push("p")
    pm2, _, svc2 = _machine(tmp_path / "B", monkeypatch, store)
    svc2.pull("p")
    svc2.push("p")
    monkeypatch.chdir(tmp_path / "A")
    with pytest.raises(SyncConflict):
        svc.push("p")
    assert svc.status()[0]["state"] == "remote-newer"
    assert svc.push("p", force=True)["version"] == 3


def test_refuses_running_profile(tmp_path, monkeypatch):
    pm, launcher, svc = _machine(tmp_path / "A", monkeypatch, tmp_path / "s")
    pm.add_profile("p", "", "linux")
    launcher.running.add("p")
    with pytest.raises(SyncError, match="Stop"):
        svc.push("p")


def test_wrong_passphrase_keeps_local_data(tmp_path, monkeypatch):
    store = tmp_path / "store"
    pm, _, svc = _machine(tmp_path / "A", monkeypatch, store)
    pm.add_profile("p", "", "linux")
    svc.push("p")
    pm2, _, svc2 = _machine(tmp_path / "B", monkeypatch, store)
    svc2.passphrase = "wrong"
    with pytest.raises(SyncError):
        svc2.pull("p")
    assert "p" not in pm2.profiles


def test_auto_flag_persists_and_shows_in_status(tmp_path, monkeypatch):
    pm, _, svc = _machine(tmp_path / "A", monkeypatch, tmp_path / "s")
    pm.add_profile("p", "", "linux")
    svc.push("p")
    assert not svc.is_auto("p")
    svc.set_auto("p", True)
    assert svc.is_auto("p") and svc.status()[0]["auto"] is True
    svc.set_auto("p", False)
    assert not svc.is_auto("p")


def test_pull_over_leftover_data_dir_without_profile_entry(tmp_path, monkeypatch):
    store = tmp_path / "store"
    pm, _, svc = _machine(tmp_path / "A", monkeypatch, store)
    pm.add_profile("p", "", "linux")
    (tmp_path / "A" / "camoufox_data" / "p" / "cookies.sqlite").write_bytes(b"NEW")
    svc.push("p")
    pm2, _, svc2 = _machine(tmp_path / "B", monkeypatch, store)
    stale = tmp_path / "B" / "camoufox_data" / "p"
    stale.mkdir(parents=True)
    (stale / "old.txt").write_text("stale")
    svc2.pull("p")
    assert (stale / "cookies.sqlite").read_bytes() == b"NEW"
    assert not (stale / "old.txt").exists()


def test_slim_pack_keeps_logins_and_drops_rebuildable_data(tmp_path):
    import zipfile

    from src.models.profile import Profile
    from src.services.profile.transfer import export_to_zip

    d = tmp_path / "data"
    keep = ["cookies.sqlite", "storage/default/https+++mail.google.com/idb/x.sqlite"]
    drop = [
        "gmp-widevinecdm/4.10/widevinecdm.dll",
        "storage/default/https+++mail.google.com/cache/morgue/1/a.final",
        "storage/default/moz-extension+++abc/idb/x.sqlite",
        "favicons.sqlite",
        "startupCache/scriptCache.bin",
    ]
    for rel in keep + drop:
        f = d / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x")
    ok, z = export_to_zip(
        Profile(name="p"), str(d), str(tmp_path), True, slim=True, filename="p.zip"
    )
    names = {n.removeprefix("data/") for n in zipfile.ZipFile(z).namelist()}
    assert set(keep) <= names
    assert not names & set(drop)


def test_store_fallback_list_and_usb_lookup(tmp_path, monkeypatch):
    from src.services.sync import backends

    missing = tmp_path / "no" / "such" / "share"
    good = tmp_path / "lan"
    good.mkdir()
    backend, label = backends.resolve_backend(f"{missing};{good}")
    assert isinstance(backend, backends.FolderBackend) and str(good) in label

    stick = tmp_path / "stick"
    stick.mkdir()
    monkeypatch.setattr(backends, "_usb_roots", lambda: [stick])
    monkeypatch.setattr(backends, "_drive_type", lambda root: 2)
    backend, label = backends.resolve_backend(f"{missing};usb:foxprofile-sync")
    assert label.startswith("USB") and (stick / "foxprofile-sync").is_dir()
    backend.write("x.json", b"{}")
    # next time the same folder is found again, whatever the drive letter is called
    other = tmp_path / "other"
    (other / "foxprofile-sync").mkdir(parents=True)
    monkeypatch.setattr(backends, "_usb_roots", lambda: [other, stick])
    assert backends.find_usb_folder("foxprofile-sync") == other / "foxprofile-sync"

    monkeypatch.setattr(backends, "_usb_roots", lambda: [])
    with pytest.raises(backends.SyncError, match="No sync store is reachable"):
        backends.resolve_backend(f"{missing};usb:foxprofile-sync")


def test_service_switches_store_when_the_first_goes_away(tmp_path, monkeypatch):
    from src.services.sync import service as svc_mod

    lan, stick = tmp_path / "net" / "lan", tmp_path / "stick"
    lan.mkdir(parents=True)
    stick.mkdir()
    monkeypatch.setattr(svc_mod, "SYNC_URL", f"{lan};{stick}")
    pm, launcher, _ = _machine(tmp_path / "A", monkeypatch, tmp_path / "unused")
    svc = SyncService(pm, launcher, passphrase="pw", state_file=str(tmp_path / "A" / "s.json"))
    assert str(lan) in (svc.backend and svc.store_label)
    import shutil

    shutil.rmtree(lan.parent)  # the share's PC went away
    assert svc.backend and str(stick) in svc.store_label


def test_every_sync_action_is_logged_with_timings(tmp_path, monkeypatch):
    store = tmp_path / "store"
    pm, _, svc = _machine(tmp_path / "A", monkeypatch, store)
    pm.add_profile("p", "", "windows")
    (tmp_path / "A" / "camoufox_data" / "p" / "cookies.sqlite").write_bytes(b"x" * 5000)
    svc.push("p", trigger="auto-stop")
    pushed = svc.log.tail()[0]
    pm2, _, svc2 = _machine(tmp_path / "B", monkeypatch, store)
    svc2.pull("p", trigger="auto-launch")
    svc2.pull("p", trigger="manual")
    with pytest.raises(SyncError):
        svc2.push("nope")

    assert pushed["event"] == "sync_push" and pushed["ok"] and pushed["trigger"] == "auto-stop"
    assert pushed["version"] == 1 and pushed["bytes"] > 0
    assert {"check_s", "pack_s", "encrypt_s", "upload_s", "total_s"} <= set(pushed)
    events = svc2.log.tail()
    assert [(e["event"], e["ok"]) for e in events] == [
        ("sync_push", False),
        ("sync_pull", True),
        ("sync_pull", True),
    ]
    assert events[2]["trigger"] == "auto-launch" and "download_s" in events[2]
    assert events[1]["skipped"] == "already up to date"
    assert "not found" in events[0]["error"]
