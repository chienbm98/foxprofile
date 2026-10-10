"""The CLI runs one macro per call, prints its result as JSON and maps the status to an exit code."""

import json
from datetime import datetime, timedelta

import pytest

from tqd_automation import __main__ as cli
from tqd_automation import client, overview
from tqd_automation.guards import TZ, Guards
from tqd_automation.judge import Verdict
from tqd_automation.platforms import facebook, tiktok, x
from tqd_automation.result import PostResult

NOW = datetime(2026, 10, 10, 9, 0, tzinfo=TZ)
TEXT = "Chào buổi sáng, Sài Gòn ☀️\nHôm nay trời đẹp quá #tqd"
STATUS_KEYS = {
    "platform",
    "profile",
    "sent_today",
    "daily_cap",
    "next_allowed_in_min",
    "locked_out",
    "kill_switch",
    "recent",
}


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("TQD_AUTOMATION_DIR", str(tmp_path / "automation_data"))
    for key in ("TQD_AUTOMATION_DISABLED", "TQD_MIN_INTERVAL_MIN", "TQD_FACEBOOK_DAILY_CAP"):
        monkeypatch.delenv(key, raising=False)
    # Loading the real .env would leak its API token into the other tests' environment.
    monkeypatch.setattr(client, "configure_from_env", lambda: None)


@pytest.fixture
def text_file(tmp_path):
    path = tmp_path / "post.txt"
    path.write_text(TEXT, encoding="utf-8")
    return str(path)


@pytest.fixture
def calls(monkeypatch):
    """Patch every macro to record its arguments and return the status in `calls['status']`."""
    seen = {"status": "published"}

    def fake(name):
        def post(*args, **kwargs):
            seen[name] = (args, kwargs)
            return PostResult(seen["status"], url="https://example.com/p/1")

        return post

    for module in (facebook, tiktok, x):
        monkeypatch.setattr(module, "post", fake(module.PLATFORM))
    return seen


def run(argv, capsys, **kw):
    code = cli.main(argv, **kw)
    return code, json.loads(capsys.readouterr().out)


@pytest.mark.parametrize(
    ("status", "code"),
    [
        ("published", 0),
        ("dry_run", 0),
        ("awaiting_approval", 0),
        ("blocked", 2),
        ("needs_agent", 3),
        ("failed", 1),
    ],
)
def test_exit_code_follows_the_status(calls, capsys, text_file, status, code):
    calls["status"] = status
    argv = ["post", "facebook", "--profile", "fb", "--text-file", text_file]
    assert run(argv, capsys) == (code, {**_result(status)})


def _result(status):
    return {
        "status": status,
        "url": "https://example.com/p/1",
        "evidence": "",
        "detail": "",
        "snapshot": "",
    }


def test_text_file_reaches_the_macro_unchanged(calls, capsys, text_file):
    run(["post", "facebook", "--profile", "fb", "--text-file", text_file], capsys)
    args, kwargs = calls["facebook"]
    assert kwargs["text"] == TEXT


def test_text_file_with_bom_loses_only_the_bom(calls, capsys, tmp_path):
    path = tmp_path / "bom.txt"
    path.write_text(TEXT, encoding="utf-8-sig")
    run(["post", "x", "--profile", "xm", "--text-file", str(path)], capsys)
    assert calls["x"][1]["text"] == TEXT


def test_facebook_options(calls, capsys, text_file):
    argv = ["post", "facebook", "--profile", "fb", "--text-file", text_file]
    argv += ["--media", "media_outbox/a.png", "media_outbox/b.png", "--audience", "only_me"]
    run([*argv, "--dry-run"], capsys)
    assert calls["facebook"][1] == {
        "profile": "fb",
        "text": TEXT,
        "images": ["media_outbox/a.png", "media_outbox/b.png"],
        "audience": "only_me",
        "dry_run": True,
    }


def test_tiktok_options(calls, capsys, text_file):
    argv = ["post", "tiktok", "--profile", "tt", "--text-file", text_file]
    run([*argv, "--media", "media_outbox/a.png", "--visibility", "only_me"], capsys)
    assert calls["tiktok"][1] == {
        "profile": "tt",
        "caption": TEXT,
        "media": ["media_outbox/a.png"],
        "visibility": "only_me",
        "dry_run": False,
    }


def test_x_options(calls, capsys, text_file):
    run(["post", "x", "--profile", "xm", "--text-file", text_file], capsys)
    assert calls["x"][1] == {"profile": "xm", "text": TEXT, "media": [], "dry_run": False}


@pytest.mark.parametrize("content", [None, "  \n"])
def test_missing_or_empty_text_fails_without_posting(calls, capsys, tmp_path, content):
    path = tmp_path / "post.txt"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    code, out = run(["post", "facebook", "--profile", "fb", "--text-file", str(path)], capsys)
    assert code == 1 and out["status"] == "failed"
    assert "facebook" not in calls


def record(g, platform, profile, minutes_ago, status="published"):
    when = Guards(now=lambda: NOW - timedelta(minutes=minutes_ago))
    when.record(
        attempt_id=g.new_attempt(),
        platform=platform,
        profile=profile,
        status=status,
        post_clicked=status != "blocked",
        text=f"{platform} {minutes_ago}",
    )


def test_status_reports_each_account(capsys):
    g = Guards(now=lambda: NOW)
    record(g, "facebook", "fb", 30)
    record(g, "facebook", "fb", 60 * 5)
    record(g, "x", "xm", 60 * 20)  # yesterday
    record(g, "tiktok", "tt", 10, status="blocked")
    g.lockout("tiktok", "tt", "checkpoint")

    code, out = run(["status"], capsys, guards=g)
    assert code == 0
    assert all(set(item) == STATUS_KEYS for item in out)
    by = {(i["platform"], i["profile"]): i for i in out}
    assert set(by) == {("facebook", "fb"), ("x", "xm"), ("tiktok", "tt")}

    fb = by["facebook", "fb"]
    assert (fb["sent_today"], fb["daily_cap"], fb["next_allowed_in_min"]) == (2, 3, 60)
    assert fb["locked_out"] is False and fb["kill_switch"] is False
    assert [line["status"] for line in fb["recent"]] == ["published", "published"]

    assert (by["x", "xm"]["sent_today"], by["x", "xm"]["next_allowed_in_min"]) == (0, 0)
    tt = by["tiktok", "tt"]
    assert tt["locked_out"] is True and tt["sent_today"] == 0


def test_status_waits_for_tomorrow_when_the_cap_is_reached(capsys, monkeypatch):
    monkeypatch.setenv("TQD_FACEBOOK_DAILY_CAP", "1")
    g = Guards(now=lambda: NOW)
    record(g, "facebook", "fb", 60 * 3)
    _, out = run(["status"], capsys, guards=g)
    assert out[0]["next_allowed_in_min"] == 15 * 60  # 09:00 until midnight


def test_status_shows_the_kill_switch_and_only_five_recent_lines(capsys, monkeypatch):
    monkeypatch.setenv("TQD_AUTOMATION_DISABLED", "1")
    g = Guards(now=lambda: NOW)
    for minutes in range(7):
        record(g, "x", "xm", 60 * 24 * 40 + minutes, status="blocked")
    _, out = run(["status"], capsys, guards=g)
    assert out[0]["kill_switch"] is True
    assert len(out[0]["recent"]) == 5


class FakeBrowser:
    def __init__(self, profile):
        self.profile = profile

    def evaluate(self, script):
        assert script == "location.href"
        return {"result": "https://www.facebook.com/"}

    def snapshot(self, interactive_only=False):
        return {"snapshot": '- button "Bạn đang nghĩ gì?"'}


class FakeJudge:
    def page_state(self, platform, url, snapshot):
        return Verdict("READY", 0.9, "heuristic", f"{platform} {url} {snapshot[:8]}")


def test_state_judges_the_open_page(capsys, monkeypatch):
    monkeypatch.setattr(client, "Browser", FakeBrowser)
    monkeypatch.setattr(overview, "make_judge", FakeJudge)
    code, out = run(["state", "--profile", "fb", "--platform", "facebook"], capsys)
    assert code == 0
    assert out == {
        "label": "READY",
        "confidence": 0.9,
        "source": "heuristic",
        "detail": "facebook https://www.facebook.com/ - button",
        "url": "https://www.facebook.com/",
    }
