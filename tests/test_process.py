import asyncio
import json
import os
import pathlib
import subprocess
import sys
import time
import types

import pytest

from src.models.profile import Profile
from src.services.browser import display, process, runner

linux_only = pytest.mark.skipif(
    not pathlib.Path("/proc/self/stat").exists(), reason="Xvfb records read /proc (Linux)"
)


# --- runner: owns the virtual display -------------------------------------------------


class FakeDisplay:
    instances: list["FakeDisplay"] = []
    fail_on_init = False

    def __init__(self):
        if FakeDisplay.fail_on_init:
            raise RuntimeError("bad CAMOUFOX_VIRTUAL_DISPLAY_SIZE")
        self.killed = 0
        self.proc = types.SimpleNamespace(pid=4242)
        FakeDisplay.instances.append(self)

    def get(self):
        return ":99"

    def kill(self):
        self.killed += 1


def _patch_launch(monkeypatch, tmp_path, headless):
    FakeDisplay.instances.clear()
    FakeDisplay.fail_on_init = False
    seen = {"config": {}, "records": []}

    def failing_camoufox(**config):
        seen["config"].update(config)
        raise RuntimeError("bad launch options")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner, "HEADLESS", headless)
    monkeypatch.setattr(runner, "VirtualDisplay", FakeDisplay)
    monkeypatch.setattr(runner, "AsyncCamoufox", failing_camoufox)
    monkeypatch.setattr(runner, "load_or_create", lambda *_: {})
    # No network: the exit-IP lookup (when present) is not under test here.
    monkeypatch.setattr(runner, "exit_ip", lambda *_: "5.6.7.8", raising=False)
    monkeypatch.setattr(runner.xvfb, "sweep_stale", lambda: seen["records"].append("sweep"))
    monkeypatch.setattr(
        runner.xvfb, "record", lambda pid, d: seen["records"].append(("record", pid, d))
    )
    monkeypatch.setattr(runner.xvfb, "clear", lambda: seen["records"].append("clear"))
    return seen


def test_virtual_display_is_stopped_when_the_launch_fails(monkeypatch, tmp_path, capsys):
    seen = _patch_launch(monkeypatch, tmp_path, "virtual")
    assert asyncio.run(runner.run_browser("p", "None", "windows")) == 1

    assert "LAUNCH_FAILED: RuntimeError: bad launch options" in capsys.readouterr().out
    assert seen["config"]["headless"] is False
    assert seen["config"]["virtual_display"] == ":99"
    assert [d.killed for d in FakeDisplay.instances] == [1]
    assert seen["records"] == ["sweep", ("record", 4242, ":99"), "clear"]


def test_virtual_display_setup_error_reports_launch_failed(monkeypatch, tmp_path, capsys):
    _patch_launch(monkeypatch, tmp_path, "virtual")
    FakeDisplay.fail_on_init = True
    assert asyncio.run(runner.run_browser("p", "None", "windows")) == 1
    assert "LAUNCH_FAILED: RuntimeError: bad CAMOUFOX_VIRTUAL_DISPLAY_SIZE" in (
        capsys.readouterr().out
    )


def test_dead_proxy_fails_before_any_virtual_display(monkeypatch, tmp_path, capsys):
    seen = _patch_launch(monkeypatch, tmp_path, "virtual")

    def dead_proxy(*_):
        raise RuntimeError("Failed to get IP address")

    monkeypatch.setattr(runner, "exit_ip", dead_proxy)
    assert asyncio.run(runner.run_browser("p", "socks5://1.2.3.4:1080", "windows")) == 1
    assert "LAUNCH_FAILED: RuntimeError: Failed to get IP address" in capsys.readouterr().out
    assert FakeDisplay.instances == []
    assert seen["records"] == []


def test_no_virtual_display_outside_virtual_mode(monkeypatch, tmp_path):
    seen = _patch_launch(monkeypatch, tmp_path, True)
    asyncio.run(runner.run_browser("p", "None", "windows"))

    assert FakeDisplay.instances == []
    assert seen["config"]["headless"] is True
    assert "virtual_display" not in seen["config"]
    assert seen["records"] == []


def test_runners_share_the_launcher_session(monkeypatch):
    # A separate session would detach runners from the terminal: no Ctrl+C,
    # and closing the terminal would orphan their browsers.
    captured = {}
    monkeypatch.setattr(process.subprocess, "Popen", lambda args, **kw: captured.update(kw))
    process.spawn_browser(Profile(name="p"))
    assert not captured.get("start_new_session")


# --- display records: platform independent ---------------------------------------------


def test_records_are_a_no_op_without_proc(monkeypatch, tmp_path):
    monkeypatch.setattr(display, "_PROC", tmp_path / "no-proc")
    monkeypatch.setattr(display.tempfile, "gettempdir", lambda: str(tmp_path))
    display.record(os.getpid(), ":5")
    display.clear()
    assert display.stop_for_runner(12345) is False
    assert display.sweep_stale() == 0
    assert list(tmp_path.iterdir()) == []


def test_cleanup_waits_for_the_runner_to_exit(monkeypatch):
    called = []
    monkeypatch.setattr(process.display, "stop_for_runner", called.append)
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        process.cleanup(proc)
        assert called == []
    finally:
        proc.kill()
        proc.wait()
    process.cleanup(proc)
    assert called == [proc.pid]


# --- display records: Linux ------------------------------------------------------------

# A stand-in for Xvfb: renames itself (comm) to "Xvfb" and optionally ignores SIGTERM.
_FAKE_XVFB = (
    "import ctypes, signal, sys, time\n"
    "ctypes.CDLL(None).prctl(15, b'Xvfb', 0, 0, 0)\n"
    "if sys.argv[1] == 'stubborn':\n"
    "    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
    "print('ready', flush=True)\n"
    "time.sleep(60)\n"
)


def _spawn(kind="xvfb"):
    if kind == "plain":
        return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    proc = subprocess.Popen(
        [sys.executable, "-c", _FAKE_XVFB, kind], stdout=subprocess.PIPE, text=True
    )
    assert proc.stdout.readline().strip() == "ready"
    return proc


def _dead_pid():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def _write_record(run_dir, runner_pid, runner_start, xvfb_pid, xvfb_start, display_no=99):
    data = {
        "runner": [runner_pid, runner_start],
        "xvfb": [xvfb_pid, xvfb_start],
        "display": display_no,
    }
    path = run_dir / f"{runner_pid}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def run_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(display.tempfile, "gettempdir", lambda: str(tmp_path))
    path = display._run_dir()
    assert path is not None
    return path


@pytest.fixture
def procs():
    started = []
    yield started
    for proc in started:
        proc.kill()
        proc.wait()


def _start(pid):
    return display._proc_stat(pid)[1]


def _gone(proc, timeout=5.0):
    deadline = time.monotonic() + timeout
    while proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    return proc.poll() is not None


@linux_only
def test_stop_for_runner_stops_the_recorded_xvfb(run_dir, procs):
    xvfb = _spawn()
    procs.append(xvfb)
    runner_pid = _dead_pid()
    path = _write_record(run_dir, runner_pid, 1, xvfb.pid, _start(xvfb.pid))

    assert display.stop_for_runner(runner_pid) is True
    assert _gone(xvfb)
    assert not path.exists()


def _stubborn_kill(run_dir, procs, lock_pid_of):
    xvfb = _spawn("stubborn")
    procs.append(xvfb)
    runner_pid = _dead_pid()
    display_no = 90000 + os.getpid() % 9000
    lock = pathlib.Path(f"/tmp/.X{display_no}-lock")
    lock.write_text(f"{lock_pid_of(xvfb):10d}\n")
    try:
        _write_record(run_dir, runner_pid, 1, xvfb.pid, _start(xvfb.pid), display_no)
        assert display.stop_for_runner(runner_pid, grace=0.2) is True
        assert _gone(xvfb)
        return lock.exists()
    finally:
        lock.unlink(missing_ok=True)


@linux_only
def test_stubborn_xvfb_is_killed_and_its_display_files_removed(run_dir, procs):
    assert _stubborn_kill(run_dir, procs, lambda xvfb: xvfb.pid) is False


@linux_only
def test_display_files_another_xvfb_took_over_are_kept(run_dir, procs):
    # The number was reused by a new Xvfb between our kill and the cleanup.
    assert _stubborn_kill(run_dir, procs, lambda xvfb: os.getpid()) is True


@linux_only
def test_a_live_runner_keeps_its_xvfb(run_dir, procs):
    # A relaunch reusing the PID, or a cleanup racing a new runner: the record
    # belongs to a process that is still running, so nothing is touched.
    xvfb = _spawn()
    live_runner = _spawn("plain")
    procs += [xvfb, live_runner]
    path = _write_record(
        run_dir, live_runner.pid, _start(live_runner.pid), xvfb.pid, _start(xvfb.pid)
    )

    assert display.stop_for_runner(live_runner.pid) is False
    assert display.sweep_stale() == 0
    assert xvfb.poll() is None
    assert path.exists()


@linux_only
def test_a_reused_xvfb_pid_is_never_killed(run_dir, procs):
    # The recorded PID now belongs to another Xvfb (another profile's display):
    # its start time differs, so it is left alone and the stale record dropped.
    other_xvfb = _spawn()
    procs.append(other_xvfb)
    runner_pid = _dead_pid()
    path = _write_record(run_dir, runner_pid, 1, other_xvfb.pid, _start(other_xvfb.pid) - 1)

    assert display.stop_for_runner(runner_pid) is False
    assert other_xvfb.poll() is None
    assert not path.exists()


@linux_only
def test_a_process_that_is_not_xvfb_is_never_killed(run_dir, procs):
    plain = _spawn("plain")
    procs.append(plain)
    runner_pid = _dead_pid()
    _write_record(run_dir, runner_pid, 1, plain.pid, _start(plain.pid))

    assert display.stop_for_runner(runner_pid) is False
    assert plain.poll() is None


@linux_only
def test_sweep_stops_only_xvfbs_of_dead_runners(run_dir, procs):
    orphan, kept = _spawn(), _spawn()
    live_runner = _spawn("plain")
    procs += [orphan, kept, live_runner]
    _write_record(run_dir, _dead_pid(), 1, orphan.pid, _start(orphan.pid))
    _write_record(run_dir, live_runner.pid, _start(live_runner.pid), kept.pid, _start(kept.pid))
    (run_dir / "777.json").write_text("{broken", encoding="utf-8")
    (run_dir / f".{_dead_pid()}.tmp").write_text("{", encoding="utf-8")
    (run_dir / f".{live_runner.pid}.tmp").write_text("{", encoding="utf-8")

    assert display.sweep_stale() == 1
    assert _gone(orphan)
    assert kept.poll() is None
    assert sorted(p.name for p in run_dir.iterdir()) == [
        f".{live_runner.pid}.tmp",
        f"{live_runner.pid}.json",
    ]


@linux_only
def test_record_and_clear_round_trip(run_dir, procs):
    xvfb = _spawn()
    procs.append(xvfb)
    display.record(xvfb.pid, ":42")
    path = run_dir / f"{os.getpid()}.json"
    rec = display._load(path)
    assert rec["runner"] == (os.getpid(), _start(os.getpid()))
    assert rec["xvfb"] == (xvfb.pid, _start(xvfb.pid))
    assert rec["display"] == 42
    display.clear()
    assert not path.exists()


@linux_only
def test_a_run_dir_others_can_read_is_not_trusted(monkeypatch, tmp_path):
    monkeypatch.setattr(display.tempfile, "gettempdir", lambda: str(tmp_path))
    path = tmp_path / f"foxprofile-{os.getuid()}"
    path.mkdir(mode=0o755)
    path.chmod(0o755)
    assert display._run_dir() is None
