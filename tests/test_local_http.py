"""Calls to FoxProfile's own loopback processes must ignore proxy environment variables."""

import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from src.utils import local_http


class _Health(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Health)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/api/v1/health"
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def dead_proxy(monkeypatch):
    # Every request sent through this proxy fails: nothing listens on port 9.
    for name in ("HTTP_PROXY", "http_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)


def test_default_urllib_is_routed_through_the_proxy(server, dead_proxy):
    # The failure the helper exists to avoid.
    with pytest.raises(urllib.error.URLError):
        urllib.request.build_opener().open(server, timeout=5)


def test_loopback_bypasses_the_proxy(server, dead_proxy):
    with local_http.open_url(urllib.request.Request(server), 5) as response:
        assert response.read() == b"ok"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://127.0.0.1:8000/api/v1/health", True),
        ("http://localhost:8000/x", True),
        ("http://[::1]:8000/x", True),
        ("https://clients2.google.com/service/update2/crx", False),
        ("http://192.168.1.10:8000/", False),
    ],
)
def test_is_loopback_url(url, expected):
    assert local_http.is_loopback_url(url) is expected
