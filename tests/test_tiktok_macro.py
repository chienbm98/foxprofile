"""The TikTok macro posts photos or a video through TikTok Studio and clicks Post at most once."""

import json
from datetime import datetime, timedelta

import pytest

from tqd_automation.guards import TZ, Guards
from tqd_automation.judge import CompositeJudge, HeuristicJudge
from tqd_automation.platforms import tiktok
from tqd_automation.platforms.tiktok import LOCATORS as L
from tqd_automation.platforms.tiktok import post

UPLOAD = '- tab "Video" [selected]\n- tab "Ảnh"\n- button "Chọn video"'
FORM = '- combobox:\n  - text: Mọi người\n- button "Đăng"\n- button "Hủy bỏ"'
POST_URL = "https://www.tiktok.com/@someone/photo/7600000000000000000"
NOW = datetime(2026, 10, 10, 19, 30, tzinfo=TZ)
REQUIRED = {
    "photo_tab",
    "video_tab",
    "file_input",
    "caption",
    "visibility_button",
    "visibility_only_me",
    "post_button",
    "discard_button",
    "discard_confirm",
    "posts_list_url",
}


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("TQD_AUTOMATION_DIR", str(tmp_path / "automation_data"))
    for key in ("TQD_AUTOMATION_DISABLED", "TQD_REQUIRE_APPROVAL", "TQD_MIN_INTERVAL_MIN"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(tiktok, "pause", lambda *a: None)
    monkeypatch.setattr(tiktok, "_sleep", lambda s: None)


class FakeBrowser:
    def __init__(
        self,
        upload_page=UPLOAD,
        ready_after=1,
        caption_sticks=True,
        after_post="redirect",
        listed=True,
    ):
        self.url, self.page = "about:blank", ""
        self.upload_page = upload_page
        self.ready_after = ready_after  # polls until the Post button is enabled; None = never
        self.caption_sticks = caption_sticks
        self.after_post = after_post  # "redirect" | "modal" | "stay"
        self.listed = listed
        self.caption_text = ""
        self.polls = 0
        self.posted = False
        self.calls = []

    def ensure_running(self):
        self.calls.append(("ensure_running",))

    def navigate(self, url):
        self.calls.append(("navigate", url))
        self.url = url
        self.page = self.upload_page if "upload" in url else ""

    def snapshot(self, interactive_only=False):
        return {"snapshot": self.page}

    def click(self, selector, timeout=10_000):
        self.calls.append(("click", selector))
        if selector == L["post_button"]:
            self.posted = True
            if self.after_post == "redirect":
                self.url = "https://www.tiktok.com" + L["posts_list_url"]

    def press(self, key):
        self.calls.append(("press", key))

    def keyboard_type(self, text):
        self.calls.append(("type", text))
        if self.caption_sticks:
            self.caption_text = text

    def upload(self, selector, paths):
        self.calls.append(("upload", selector, paths))
        self.page = FORM

    def wait_for(self, selector, timeout=15_000):
        self.calls.append(("wait_for", selector))

    def screenshot_png(self):
        return b"\x89PNG"

    def evaluate(self, script):
        if script == "location.href":
            return {"result": self.url}
        if script == tiktok.POST_ENABLED:
            self.polls += 1
            return {"result": self.ready_after is not None and self.polls >= self.ready_after}
        if script == tiktok.CAPTION_TEXT:
            return {"result": self.caption_text}
        if script == tiktok.MODAL_TEXT:
            return {"result": "Kiểm tra nội dung" if self.after_post == "modal" else ""}
        if "/video/" in script:
            return {"result": POST_URL if self.listed else ""}
        raise AssertionError(f"unexpected script {script[:40]}")

    def clicks(self, key):
        return sum(1 for c in self.calls if c == ("click", L[key]))


def run(browser, text="Chào buổi tối #tqd", media=("media_outbox/a.png",), **kw):
    guards = kw.pop("guards", Guards(now=lambda: NOW))
    return post(
        "tt",
        text,
        list(media),
        browser=browser,
        judge=CompositeJudge(HeuristicJudge()),
        guards=guards,
        **kw,
    )


def ledger(tmp_path):
    path = tmp_path / "automation_data" / "post_ledger.jsonl"
    return [json.loads(x) for x in path.read_text("utf-8").splitlines()] if path.exists() else []


def test_locators_are_complete():
    assert set(L) >= REQUIRED and all(L[k] for k in REQUIRED)


def test_guard_block_makes_no_browser_calls(monkeypatch):
    monkeypatch.setenv("TQD_AUTOMATION_DISABLED", "1")
    b = FakeBrowser()
    assert run(b).status == "blocked"
    assert b.calls == []


def test_caption_over_limit_is_blocked():
    b = FakeBrowser()
    assert run(b, text="x" * 2201).status == "blocked"
    assert b.calls == []


@pytest.mark.parametrize(
    "media",
    [
        (),
        ("media_outbox/a.png", "media_outbox/b.mp4"),
        ("media_outbox/a.mp4", "media_outbox/b.mp4"),
    ],
)
def test_media_must_be_photos_or_one_video(media):
    b = FakeBrowser()
    result = run(b, media=media)
    assert result.status == "failed" and "media" in result.detail
    assert b.calls == []


def test_captcha_locks_out(tmp_path):
    b = FakeBrowser(upload_page='- heading "Drag the puzzle piece"\n- text: captcha')
    result = run(b)
    assert result.status == "blocked"
    assert (tmp_path / "automation_data" / "lockout_tiktok_tt").exists()
    assert b.clicks("post_button") == 0


def test_unknown_page_needs_agent():
    result = run(FakeBrowser(upload_page="- heading 'Something new'"))
    assert result.status == "needs_agent" and result.snapshot


def test_photos_use_the_photo_tab():
    b = FakeBrowser()
    run(b, media=("media_outbox/a.png", "media_outbox/b.jpg"))
    assert b.clicks("photo_tab") == 1
    assert ("upload", L["file_input"], ["media_outbox/a.png", "media_outbox/b.jpg"]) in b.calls


def test_video_stays_on_the_video_tab():
    b = FakeBrowser()
    assert run(b, media=("media_outbox/a.mp4",)).status == "published"
    assert b.clicks("photo_tab") == 0


def test_upload_never_finishing_fails_before_post(tmp_path):
    b = FakeBrowser(ready_after=None)
    result = run(b)
    assert result.status == "failed" and "upload not finished" in result.detail
    assert b.clicks("post_button") == 0
    assert all(not x["post_clicked"] for x in ledger(tmp_path))


def test_caption_not_taken_needs_agent():
    b = FakeBrowser(caption_sticks=False)
    assert run(b).status == "needs_agent"
    assert b.clicks("post_button") == 0


def test_dry_run_never_clicks_post(tmp_path):
    b = FakeBrowser()
    result = run(b, visibility="only_me", dry_run=True)
    assert result.status == "dry_run" and result.evidence
    assert b.clicks("post_button") == 0
    assert b.clicks("visibility_only_me") == 1
    assert b.clicks("discard_confirm") == 1


def test_happy_path_publishes_once(tmp_path):
    b = FakeBrowser()
    result = run(b)
    assert result.status == "published" and result.url == POST_URL
    names = [c[0] for c in b.calls]
    assert names.index("upload") < names.index("type")
    assert ("press", "Control+A") in b.calls
    assert b.clicks("post_button") == 1
    lines = ledger(tmp_path)
    assert [(x["status"], x["post_clicked"]) for x in lines] == [
        ("pending", True),
        ("published", True),
    ]


def test_modal_after_post_is_unconfirmed_and_not_clicked(tmp_path):
    b = FakeBrowser(after_post="modal")
    result = run(b)
    assert result.status == "failed" and "publish unconfirmed" in result.detail
    assert "Kiểm tra nội dung" in result.detail
    assert b.clicks("post_button") == 1
    assert ledger(tmp_path)[-1]["post_clicked"] is True


def test_no_redirect_after_post_is_unconfirmed(tmp_path):
    b = FakeBrowser(after_post="stay")
    result = run(b)
    assert result.status == "failed" and "publish unconfirmed" in result.detail
    assert b.clicks("post_button") == 1


def test_post_not_listed_yet_is_still_published(tmp_path, monkeypatch):
    b = FakeBrowser(listed=False)
    result = run(b)
    assert result.status == "published" and result.url == ""
    monkeypatch.setenv("TQD_MIN_INTERVAL_MIN", "0")
    again = FakeBrowser()
    later = Guards(now=lambda: NOW + timedelta(minutes=1))
    assert run(again, guards=later).detail == "duplicate text"
    assert again.calls == []
