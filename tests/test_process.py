import asyncio
import os
import subprocess
import sys
import time
import types

import pytest

from src.services.browser import display, process, runner


class FakeDisplay:
    instances: list["FakeDisplay"] = []

    def __init__(self):
        self.killed = 0
        self.proc = types.SimpleNamespace(pid=4242)
        FakeDisplay.instances.append(self)

    def get(self):
        return ":99"

    def kill(self):
        self.killed += 1


def _patch_launch(monkeypatch, tmp_path, headless, camoufox):
    FakeDisplay.instances.clear()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner, "HEADLESS", headless)
    monkeypatch.setattr(runner, "VirtualDisplay", FakeDisplay)
    monkeypatch.setattr(runner, "AsyncCamoufox", camoufox)
    monkeypatch.setattr(runner, "load_or_create", lambda *_: {})


def test_virtual_display_is_stopped_when_the_launch_fails(monkeypatch, tmp_path, capsys):
    seen = {}

    def failing_camoufox(**config):
        seen.update(config)
        raise RuntimeError("bad launch options")

    _patch_launch(monkeypatch, tmp_path, "virtual", failing_camoufox)
    assert asyncio.run(runner.run_browser("p", "None", "windows")) == 1

    assert "LAUNCH_FAILED: RuntimeError: bad launch options" in capsys.readouterr().out
    assert seen["headless"] is False
    assert seen["virtual_display"] == ":99"
    assert [d.killed for d in FakeDisplay.instances] == [1]
    # The runner stopped its own Xvfb, so nothing is left for the launcher to stop.
    assert not display.pid_path(str(tmp_path / "camoufox_data" / "p")).exists()


def test_no_virtual_display_outside_virtual_mode(monkeypatch, tmp_path):
    seen = {}

    def failing_camoufox(**config):
        seen.update(config)
        raise RuntimeError("x")

    _patch_launch(monkeypatch, tmp_path, True, failing_camoufox)
    asyncio.run(runner.run_browser("p", "None", "windows"))

    assert FakeDisplay.instances == []
    assert seen["headless"] is True
    assert "virtual_display" not in seen


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX only")
def test_terminate_kills_what_the_runner_left_in_its_group():
    # A "runner" that starts a long-lived helper (like Xvfb) and ignores SIGTERM,
    # so terminate() has to force-kill it and the helper would otherwise survive.
    script = (
        "import signal, subprocess, sys, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "helper = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "print(helper.pid, flush=True)\n"
        "time.sleep(60)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    helper_pid = int(proc.stdout.readline())
    assert _alive(helper_pid)

    process.terminate(proc, "p", timeout=1)

    deadline = time.monotonic() + 5
    while _alive(helper_pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _alive(helper_pid)


def test_cleanup_leaves_a_running_runner_alone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    display.record(str(tmp_path / "camoufox_data" / "p"), 1234)
    try:
        process.cleanup(proc, "p")
        assert proc.poll() is None
        assert display.pid_path(str(tmp_path / "camoufox_data" / "p")).exists()
    finally:
        proc.kill()
        proc.wait()


def test_stop_recorded_never_kills_a_process_that_is_not_xvfb(tmp_path):
    # A recorded PID that now belongs to something else (PID reuse) is left alone.
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        display.record(str(tmp_path), proc.pid)
        assert display.stop_recorded(str(tmp_path)) is False
        assert proc.poll() is None
        assert not display.pid_path(str(tmp_path)).exists()
    finally:
        proc.kill()
        proc.wait()


def test_stop_recorded_without_a_record(tmp_path):
    assert display.stop_recorded(str(tmp_path)) is False
