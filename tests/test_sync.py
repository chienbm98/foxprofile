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
