"""Sync backends against real servers: a WebDAV server (wsgidav) and an S3 server (moto)."""

import socket
import threading
import time

import pytest

from src.services.profile.manager import ProfileManager
from src.services.sync.backends import S3Backend, WebDAVBackend, open_backend
from src.services.sync.service import SyncService


def _port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait(port):
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("server did not start")


@pytest.fixture
def webdav(tmp_path):
    pytest.importorskip("wsgidav")
    from cheroot import wsgi
    from wsgidav.wsgidav_app import WsgiDAVApp

    root = tmp_path / "dav"
    root.mkdir()
    port = _port()
    app = WsgiDAVApp(
        {
            "host": "127.0.0.1",
            "port": port,
            "provider_mapping": {"/": str(root)},
            "simple_dc": {"user_mapping": {"*": {"u": {"password": "p"}}}},
            "http_authenticator": {"accept_basic": True, "default_to_digest": False},
            "verbose": 0,
        }
    )
    server = wsgi.Server(("127.0.0.1", port), app)
    threading.Thread(target=server.safe_start, daemon=True).start()
    _wait(port)
    yield f"webdav://u:p@127.0.0.1:{port}/foxprofile"
    server.stop()


@pytest.fixture
def s3(monkeypatch):
    pytest.importorskip("moto")
    pytest.importorskip("boto3")
    from moto.server import ThreadedMotoServer

    port = _port()
    server = ThreadedMotoServer(port=port, verbose=False)
    server.start()
    endpoint = f"http://127.0.0.1:{port}"
    for k, v in (
        ("AWS_ACCESS_KEY_ID", "k"),
        ("AWS_SECRET_ACCESS_KEY", "s"),
        ("AWS_DEFAULT_REGION", "us-east-1"),
        ("FOXPROFILE_SYNC_S3_ENDPOINT", endpoint),
    ):
        monkeypatch.setenv(k, v)
    import boto3

    boto3.client("s3", endpoint_url=endpoint).create_bucket(Bucket="fox")
    yield "s3://fox/profiles"
    server.stop()


def _exercise(backend, tmp_path):
    src = tmp_path / "blob.bin"
    src.write_bytes(b"x" * 300_000)
    backend.upload("a.fpx", str(src))
    backend.write("a.json", b'{"version": 1}')
    assert backend.read("a.json") == b'{"version": 1}'
    assert backend.read("missing.json") in (None, b"")
    dst = tmp_path / "back.bin"
    backend.download("a.fpx", str(dst))
    assert dst.read_bytes() == src.read_bytes()
    assert set(backend.list()) == {"a.fpx", "a.json"}
    backend.delete("a.fpx")
    assert backend.list() == ["a.json"]


def test_webdav_backend(webdav, tmp_path):
    backend = open_backend(webdav)
    assert isinstance(backend, WebDAVBackend)
    _exercise(backend, tmp_path)


def test_s3_backend(s3, tmp_path):
    backend = open_backend(s3)
    assert isinstance(backend, S3Backend)
    _exercise(backend, tmp_path)


class _Idle:
    def is_running(self, name):
        return False


@pytest.mark.parametrize("store", ["webdav", "s3"])
def test_profile_roundtrip(store, request, tmp_path, monkeypatch):
    url = request.getfixturevalue(store)
    results = {}
    for label in ("A", "B"):
        root = tmp_path / label
        root.mkdir()
        monkeypatch.chdir(root)
        pm = ProfileManager()
        svc = SyncService(
            pm,
            _Idle(),
            backend=open_backend(url),
            passphrase="pw",
            state_file=str(root / "state.json"),
            data_dir="camoufox_data",
        )
        if label == "A":
            pm.add_profile("gmail-1", "", "windows")
            (root / "camoufox_data" / "gmail-1" / "cookies.sqlite").write_bytes(b"LOGIN")
            svc.push("gmail-1")
        else:
            svc.pull("gmail-1")
            results["cookie"] = (
                root / "camoufox_data" / "gmail-1" / "cookies.sqlite"
            ).read_bytes()
    assert results["cookie"] == b"LOGIN"
