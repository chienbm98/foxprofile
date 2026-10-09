"""The Chrome runner speaks FoxProfile's runner protocol (real browser)."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from chrome_engine.release import host_os

pytestmark = pytest.mark.browser

ROOT = Path(__file__).resolve().parents[2]


class Runner:
    def __init__(self, data_dir: Path, *args: str, restore_tabs: bool = True) -> None:
        env = {
            **os.environ,
            "FOXPROFILE_DATA_DIR": str(data_dir),
            "FOXPROFILE_HEADLESS": "true",
            "FOXPROFILE_RESTORE_TABS": "true" if restore_tabs else "false",
            "PYTHONPATH": str(ROOT),
        }
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "chrome_engine.runner", *args],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.lines: queue.Queue[str] = queue.Queue()
        self.log: list[str] = []
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        for line in self.proc.stdout:
            self.lines.put(line.rstrip("\n"))

    def wait_for(self, prefix: str, timeout: float = 60) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                line = self.lines.get(timeout=0.5)
            except queue.Empty:
                if self.proc.poll() is not None and self.lines.empty():
                    break
                continue
            self.log.append(line)
            if line.startswith(prefix):
                return line
        raise AssertionError(f"no {prefix!r} line; output:\n" + "\n".join(self.log))

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def control(port: int, token: str, action: str, **params):
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/action",
        data=json.dumps({"action": action, "params": params}).encode(),
        headers={"Content-Type": "application/json", "X-Control-Token": token},
    )
    with urllib.request.urlopen(request, timeout=30) as resp:
        body = json.loads(resp.read())
    assert body["ok"], body
    return body["result"]


@pytest.fixture
def origin_url():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = f"<html><title>page {self.path}</title><body>ok</body></html>".encode()
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


def test_protocol_control_and_tab_restore(chrome_exe, tmp_path, origin_url):
    runner = Runner(tmp_path, "alice", "None", host_os(), "Asia/Tokyo", "ja-JP")
    try:
        control_line = runner.wait_for("CONTROL:")
        runner.wait_for("BROWSER_STARTED")
        # CONTROL comes before BROWSER_STARTED (the launcher relies on it).
        assert runner.log.index(control_line) < runner.log.index("BROWSER_STARTED")
        _, port, token = control_line.split(":", 2)
        port = int(port)

        page = control(port, token, "navigate", url=origin_url + "/one")
        assert page["title"] == "page /one"
        values = control(
            port,
            token,
            "evaluate",
            script="() => [Intl.DateTimeFormat().resolvedOptions().timeZone, navigator.language, navigator.webdriver]",
        )["result"]
        assert values == ["Asia/Tokyo", "ja-JP", False]
        control(port, token, "tab_new", url=origin_url + "/two")

        tabs_file = tmp_path / "alice" / "tabs.json"
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if tabs_file.exists() and len(json.loads(tabs_file.read_text("utf-8"))["tabs"]) == 2:
                break
            time.sleep(0.5)
        saved = json.loads(tabs_file.read_text("utf-8"))["tabs"]
        assert [u.rsplit("/", 1)[1] for u in saved] == ["one", "two"]
    finally:
        runner.stop()

    persona_file = tmp_path / "alice" / "chrome_persona.json"
    first_persona = json.loads(persona_file.read_text("utf-8"))

    # A hard-killed runner must not leave its browser holding the profile:
    # the second launch of the same profile has to succeed.
    runner = Runner(tmp_path, "alice", "None", host_os(), "Asia/Tokyo", "ja-JP")
    try:
        runner.wait_for("BROWSER_STARTED", timeout=90)
        assert "Restored 2 tab(s)" in runner.log
        _, port, token = next(line for line in runner.log if line.startswith("CONTROL:")).split(
            ":", 2
        )
        tabs = control(int(port), token, "tabs")["tabs"]
        assert sorted(t["title"] for t in tabs) == ["page /one", "page /two"]
    finally:
        runner.stop()
    assert json.loads(persona_file.read_text("utf-8")) == first_persona


def test_launch_failure_is_reported(chrome_exe, tmp_path):
    # A Linux persona cannot be presented on Windows; elsewhere use a bad proxy port.
    if host_os() == "windows":
        args = ("bob", "None", "linux")
        expected = "cannot be presented consistently"
    else:
        args = ("bob", "http://127.0.0.1:1", host_os())
        expected = "exit IP"
    runner = Runner(tmp_path, *args, restore_tabs=False)
    try:
        line = runner.wait_for("LAUNCH_FAILED")
        assert expected in line
        assert runner.proc.wait(30) == 1
    finally:
        runner.stop()


def test_last_tab_closing_reports_browser_closed(chrome_exe, tmp_path):
    runner = Runner(tmp_path, "carol", "None", host_os(), "", "", restore_tabs=False)
    try:
        runner.wait_for("BROWSER_STARTED")
        _, port, token = next(line for line in runner.log if line.startswith("CONTROL:")).split(
            ":", 2
        )
        control(int(port), token, "evaluate", script="() => window.close()")
        runner.wait_for("BROWSER_CLOSED", timeout=30)
        assert runner.proc.wait(30) == 0
    finally:
        runner.stop()
