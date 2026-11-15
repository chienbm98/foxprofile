"""The Proton sign-in state machine against a fake account page (real browser)."""

from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from chrome_engine.engine import ChromeEngine
from chrome_engine.release import host_os
from src.services.browser import proton_login
from src.services.proton_account import ProtonAccount

pytestmark = pytest.mark.browser

SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

PAGE = """
<!doctype html><html><body>
<script>
const mode = new URLSearchParams(location.search).get('mode') || 'login';
function wire() {
  const form = document.querySelector('form');
  if (form) form.addEventListener('submit', (event) => { event.preventDefault(); step(); });
}
function show(html) { document.body.innerHTML = html; wire(); }
function done() {
  window.postMessage({payload: {selector: 'selector-1', state: 'state-1'}}, '*');
  show('<h1>Signed in</h1>');
}
function step() {
  if (document.querySelector('#username')) {
    show('<form><input type="password" id="password"><button type="submit">Sign in</button></form>');
    return;
  }
  if (document.querySelector('#password')) {
    if (mode === 'twofa') {
      show('<p>Two-factor authentication</p><form><input id="twofa" inputmode="numeric"><button type="submit">Verify</button></form>');
      return;
    }
    done();
    return;
  }
  done();
}
document.body.innerHTML =
  '<form><input id="username"><button type="submit">Continue</button></form>';
wire();
</script>
</body></html>
"""


@pytest.fixture
def account_url():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _sign_in(chrome_exe, tmp_path, url, account):
    async def run():
        engine = ChromeEngine(
            tmp_path / "profile",
            platform=host_os(),
            headless=True,
            geoip=False,
            executable=chrome_exe,
        )
        context = await engine.start()
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            return await proton_login._sign_in(page, account)
        finally:
            await engine.stop()

    return asyncio.run(run())


def test_username_password_and_fork(chrome_exe, tmp_path, account_url):
    ok, message = _sign_in(
        chrome_exe, tmp_path, account_url, ProtonAccount("user@example.com", "secret")
    )
    assert ok, message


def test_totp_is_filled_when_the_account_asks(chrome_exe, tmp_path, account_url):
    ok, message = _sign_in(
        chrome_exe,
        tmp_path,
        f"{account_url}?mode=twofa",
        ProtonAccount("user@example.com", "secret", SECRET),
    )
    assert ok, message


def test_missing_totp_falls_back_to_a_manual_sign_in(chrome_exe, tmp_path, account_url):
    ok, message = _sign_in(
        chrome_exe,
        tmp_path,
        f"{account_url}?mode=twofa",
        ProtonAccount("user@example.com", "secret"),
    )
    assert not ok
    assert "two-factor is required" in message
