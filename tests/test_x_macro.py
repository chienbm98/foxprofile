"""The X macro posts text and up to four images, clicks Post at most once and finds the post URL."""

import json
from datetime import datetime, timedelta

import pytest

from tqd_automation.guards import TZ, Guards
from tqd_automation.judge import CompositeJudge, HeuristicJudge
from tqd_automation.platforms import x
from tqd_automation.platforms.x import LOCATORS as L
from tqd_automation.platforms.x import post

COMPOSER = '- link "Trang chủ"\n- textbox "Đăng văn bản"\n- button "Đăng" [disabled]'
POST_URL = "https://x.com/someone/status/1900000000000000000"
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=TZ)
REQUIRED = {
    "composer_url",
    "textbox",
    "file_input",
    "media_preview",
    "post_button",
    "close_button",
    "discard_button",
    "profile_link",
}


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("TQD_AUTOMATION_DIR", str(tmp_path / "automation_data"))
    for key in ("TQD_AUTOMATION_DISABLED", "TQD_REQUIRE_APPROVAL", "TQD_MIN_INTERVAL_MIN"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(x, "pause", lambda *a: None)
    monkeypatch.setattr(x, "_sleep", lambda s: None)


class FakeBrowser:
    def __init__(self, page=COMPOSER, text_sticks=True, after_post="closed", listed=True):
        self.url, self.page = "about:blank", ""
        self.composer_page = page
        self.text_sticks, self.after_post, self.listed = text_sticks, after_post, listed
        self.typed = ""
        self.dialog_open = False
        self.calls = []

    def ensure_running(self):
        self.calls.append(("ensure_running",))

    def navigate(self, url):
        self.calls.append(("navigate", url))
        self.url = url
        if url == L["composer_url"]:
            self.page, self.dialog_open = self.composer_page, True
        else:
            self.page = ""

    def snapshot(self, interactive_only=False):
        return {"snapshot": self.page}

    def click(self, selector, timeout=10_000):
        self.calls.append(("click", selector))
        if selector == L["post_button"] and self.after_post == "closed":
            self.dialog_open = False

    def press(self, key):
        self.calls.append(("press", key))

    def keyboard_type(self, text):
        self.calls.append(("type", text))
        if self.text_sticks:
            self.typed = text

    def upload(self, selector, paths):
        self.calls.append(("upload", selector, paths))

    def wait_for(self, selector, timeout=15_000):
        self.calls.append(("wait_for", selector))

    def screenshot_png(self):
        return b"\x89PNG"

    def evaluate(self, script):
        if script == "location.href":
            return {"result": self.url}
        if script == x.COMPOSER_TEXT:
            return {"result": self.typed}
        if script == x.COMPOSER_OPEN:
            return {"result": self.dialog_open}
        if script == x.ALERT_TEXT:
            toasts = {"alert": "Đã xảy ra lỗi", "sent": "Bài đăng của bạn đã được gửi.\nXem"}
            return {"result": toasts.get(self.after_post, "")}
        if script == x.TOAST_URL:
            return {"result": POST_URL if self.after_post == "sent" else ""}
        if script == x.PROFILE_HREF:
            return {"result": "/someone"}
        if "/status/" in script:
            # `listed`: on which profile lookup the post shows up (False: never).
            self.lookups = getattr(self, "lookups", 0) + 1
            return {"result": POST_URL if self.listed and self.lookups >= self.listed else ""}
        raise AssertionError(f"unexpected script {script[:40]}")

    def clicks(self, key):
        return sum(1 for c in self.calls if c == ("click", L[key]))


def run(browser, text="Chào buổi trưa", media=("media_outbox/a.png",), **kw):
    guards = kw.pop("guards", Guards(now=lambda: NOW))
    return post(
        "xm",
        text,
        list(media),
        browser=browser,
        judge=CompositeJudge(HeuristicJudge()),
        guards=guards,
        **kw,
    )


def ledger(tmp_path):
    path = tmp_path / "automation_data" / "post_ledger.jsonl"
    return (
        [json.loads(line) for line in path.read_text("utf-8").splitlines()] if path.exists() else []
    )


def test_locators_are_complete():
    assert set(L) >= REQUIRED and all(L[k] for k in REQUIRED)


def test_guard_block_makes_no_browser_calls(monkeypatch):
    monkeypatch.setenv("TQD_AUTOMATION_DISABLED", "1")
    b = FakeBrowser()
    assert run(b).status == "blocked"
    assert b.calls == []


def test_text_over_weighted_limit_is_blocked():
    b = FakeBrowser()
    assert run(b, text="ệ" * 141).status == "blocked"
    assert b.calls == []


@pytest.mark.parametrize(
    "media",
    [
        tuple(f"media_outbox/{i}.png" for i in range(5)),
        ("media_outbox/a.png", "media_outbox/b.mp4"),
        ("media_outbox/a.exe",),
    ],
)
def test_media_rules(media):
    b = FakeBrowser()
    result = run(b, media=media)
    assert result.status == "failed" and "media" in result.detail
    assert b.calls == []


def test_text_only_post_skips_upload():
    b = FakeBrowser()
    assert run(b, media=()).status == "published"
    assert not any(c[0] == "upload" for c in b.calls)


def test_locked_account_page_locks_out(tmp_path):
    b = FakeBrowser()
    b.navigate = lambda url: setattr(b, "url", "https://x.com/account/access")
    assert run(b).status == "blocked"
    assert (tmp_path / "automation_data" / "lockout_x_xm").exists()


def test_login_page_fails():
    b = FakeBrowser()
    b.navigate = lambda url: setattr(b, "url", "https://x.com/i/flow/login")
    result = run(b)
    assert result.status == "failed" and "log in" in result.detail


def test_text_not_taken_needs_agent():
    b = FakeBrowser(text_sticks=False)
    assert run(b).status == "needs_agent"
    assert b.clicks("post_button") == 0


def test_dry_run_never_clicks_post(tmp_path):
    b = FakeBrowser()
    result = run(b, dry_run=True)
    assert result.status == "dry_run" and result.evidence
    assert b.clicks("post_button") == 0
    assert b.clicks("discard_button") == 1


def test_happy_path_publishes_once(tmp_path):
    b = FakeBrowser()
    result = run(b)
    assert result.status == "published" and result.url == POST_URL
    names = [c[0] for c in b.calls]
    assert names.index("upload") < names.index("type")
    assert b.clicks("post_button") == 1
    assert ("navigate", "https://x.com/someone") in b.calls
    assert [(line["status"], line["post_clicked"]) for line in ledger(tmp_path)] == [
        ("pending", True),
        ("published", True),
    ]


@pytest.mark.parametrize(
    ("after_post", "detail"), [("open", "publish unconfirmed"), ("alert", "Đã xảy ra lỗi")]
)
def test_unconfirmed_publish(tmp_path, after_post, detail):
    b = FakeBrowser(after_post=after_post)
    result = run(b)
    assert result.status == "failed" and detail in result.detail
    assert b.clicks("post_button") == 1
    assert ledger(tmp_path)[-1]["post_clicked"] is True


def test_post_not_found_yet_is_still_published_and_blocks_a_repeat(monkeypatch):
    b = FakeBrowser(listed=False)
    result = run(b)
    assert result.status == "published" and result.url == ""
    monkeypatch.setenv("TQD_MIN_INTERVAL_MIN", "0")
    again = FakeBrowser()
    later = Guards(now=lambda: NOW + timedelta(minutes=1))
    assert run(again, guards=later).detail == "duplicate text"
    assert again.calls == []


def test_success_toast_while_composer_still_open_is_published(tmp_path):
    b = FakeBrowser(after_post="sent")
    result = run(b)
    assert result.status == "published" and result.url == POST_URL
    assert b.clicks("post_button") == 1


def test_toast_link_is_used_without_visiting_the_profile():
    b = FakeBrowser(after_post="sent")
    assert run(b).url == POST_URL
    assert not any(c[0] == "navigate" and c[1] != L["composer_url"] for c in b.calls)


def test_stale_profile_timeline_is_reloaded_until_the_post_shows():
    b = FakeBrowser(listed=3)
    assert run(b).url == POST_URL
    profile_loads = [c for c in b.calls if c == ("navigate", "https://x.com/someone")]
    assert len(profile_loads) == 3
