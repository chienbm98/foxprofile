import threading

import pytest

from src.models.profile import Profile
from src.services.browser import launcher as launcher_mod
from src.services.browser.launcher import BrowserLauncher, ProfileBusyError
from src.ui.actions.browser import launch_or_stop
from src.ui.state import AppState


class FakeProc:
    def poll(self):
        return None


@pytest.fixture
def bl(monkeypatch):
    spawned = []

    def spawn(profile):
        spawned.append(profile.name)
        return FakeProc()

    monkeypatch.setattr(launcher_mod, "spawn_browser", spawn)
    monkeypatch.setattr(launcher_mod, "wait_for_exit", lambda *a: None)
    b = BrowserLauncher()
    monkeypatch.setattr(b, "_monitor_process", lambda *a: None)
    b.spawned = spawned
    yield b
    # Fake processes must not reach terminate() at interpreter exit.
    b._active_sessions.clear()


def test_second_launch_returns_false_without_callbacks(bl):
    calls = []
    assert bl.start_thread(Profile(name="p"), lambda m: None) is True
    started = bl.start_thread(
        Profile(name="p"),
        lambda m: None,
        on_start=lambda: calls.append("start"),
        on_stop=lambda: calls.append("stop"),
    )
    assert started is False
    assert calls == []
    assert bl.spawned == ["p"]


def test_concurrent_launches_spawn_one_browser(bl, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def slow_spawn(profile):
        entered.set()
        release.wait(5)
        bl.spawned.append(profile.name)
        return FakeProc()

    monkeypatch.setattr(launcher_mod, "spawn_browser", slow_spawn)
    first = threading.Thread(target=bl.start_thread, args=(Profile(name="p"), lambda m: None))
    first.start()
    assert entered.wait(5)
    try:
        with pytest.raises(ProfileBusyError):
            bl.start_thread(Profile(name="p"), lambda m: None)
    finally:
        release.set()
        first.join(5)
    assert bl.spawned == ["p"]
    assert bl.is_running("p")


def test_failed_spawn_releases_the_profile(bl, monkeypatch):
    def broken(profile):
        raise OSError("no runner")

    monkeypatch.setattr(launcher_mod, "spawn_browser", broken)
    stopped = []
    assert bl.start_thread(Profile(name="p"), lambda m: None, on_stop=lambda: stopped.append(1))
    assert stopped == [1]
    with bl.exclusive("p"):
        pass


class _Profiles:
    def __init__(self, *names):
        self.profiles = {n: Profile(name=n) for n in names}


def test_ui_click_does_not_stay_loading_when_launched_elsewhere(bl, monkeypatch):
    state = AppState()
    # The API launched the profile between the UI's is_running check and its
    # start_thread call.
    monkeypatch.setattr(bl, "is_running", lambda name: False)
    bl.start_thread(Profile(name="p"), lambda m: None)

    launch_or_stop("p", _Profiles("p"), bl, state, lambda m: None)

    assert not state.is_loading("p")
    assert "p" not in state.failed
    assert bl.spawned == ["p"]
