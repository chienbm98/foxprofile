"""Publish photos or one video with a caption through TikTok Studio in one call.

Same safety structure as the Facebook macro (see `common.py`). TikTok Studio has a Photo tab that
takes jpg/png/webp directly, so images need no conversion to video.
"""

from __future__ import annotations

import json
import time
from pathlib import PurePath
from typing import Any, Literal

from ..guards import Guards
from ..humanize import pause
from ..judge import PageState
from ..result import PostResult
from .common import BaseRun, first_line, run_macro

PLATFORM = "tiktok"
UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload"
PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXT = {".mp4", ".mov", ".webm"}
MAX_PHOTOS = 35
UPLOAD_SECONDS = 300
PUBLISH_SECONDS = 60
LIST_ATTEMPTS = 6

# Found on the live TikTok Studio page (vi-VN UI) with English names as fallback.
LOCATORS = {
    "photo_tab": "role=tab[name=/^(Ảnh|Photos?)$/i]",
    "video_tab": "role=tab[name=/^Video$/i]",
    "file_input": "input[type=file]",
    "photo_preview": "role=button[name=/Delete photo|Xóa ảnh/i]",
    "caption": "[data-e2e=caption_container] [contenteditable=true]",
    "visibility_button": "[data-e2e=video_visibility_container] [role=combobox]",
    "visibility_only_me": "role=option[name=/Chỉ mình bạn|Only you|Only me/i]",
    "post_button": "role=button[name=/^(Đăng|Post)$/]",
    "discard_button": "role=button[name=/^(Hủy bỏ|Discard)$/i]",
    "discard_confirm": "[role=dialog] >> role=button[name=/Hủy bỏ nội dung chỉnh sửa|^Discard$/i]",
    "posts_list_url": "/tiktokstudio/content",
}

POST_ENABLED = """(() => {
  const b = [...document.querySelectorAll('button')].find(x => /^(Đăng|Post)$/.test(x.innerText.trim()));
  return !!b && !b.disabled && b.getAttribute('aria-disabled') !== 'true';
})()"""
CAPTION_TEXT = (
    "(document.querySelector('[data-e2e=caption_container] [contenteditable=true]') || {})"
    ".innerText || ''"
)
MODAL_TEXT = (
    "[...document.querySelectorAll('[role=dialog]')].map(d => d.innerText.trim())"
    ".filter(Boolean).join(' | ').slice(0, 200)"
)
# In the Studio post list each post's link text is its caption.
FIND_POST_URL = """(() => {
  const text = %s;
  const link = [...document.querySelectorAll('a[href*="/video/"], a[href*="/photo/"]')]
    .find(a => a.innerText.includes(text));
  return link ? link.href : '';
})()"""


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def post(
    profile: str,
    caption: str,
    media: list[str],
    visibility: Literal["default", "only_me"] = "default",
    dry_run: bool = False,
    browser: Any = None,
    judge: Any = None,
    guards: Guards | None = None,
) -> PostResult:
    return run_macro(_Run, profile, caption, media, visibility, dry_run, browser, judge, guards)


class _Run(BaseRun):
    platform = PLATFORM

    @property
    def photos(self) -> bool:
        return all(PurePath(m).suffix.lower() in PHOTO_EXT for m in self.media)

    def validate(self) -> str | None:
        if not self.media:
            return "TikTok needs media: photos or one video"
        if self.photos:
            return None if len(self.media) <= MAX_PHOTOS else f"at most {MAX_PHOTOS} photos"
        if len(self.media) == 1 and PurePath(self.media[0]).suffix.lower() in VIDEO_EXT:
            return None
        return "TikTok media must be photos (jpg/png/webp) or exactly one video (mp4/mov/webm)"

    def act(self, visibility: str, dry_run: bool) -> PostResult:
        self.b.navigate(UPLOAD_URL)
        pause()
        stop = self._stop_unless(PageState.READY.value, PageState.COMPOSER_OPEN.value)
        if stop:
            return stop

        if self.photos:
            self.b.click(LOCATORS["photo_tab"])
            pause()
        self.b.upload(LOCATORS["file_input"], self.media)
        if self.photos:
            self.b.wait_for(LOCATORS["photo_preview"])
        for _ in range(UPLOAD_SECONDS):
            if self.b.evaluate(POST_ENABLED)["result"]:
                break
            _sleep(1)
        else:
            return self._end("failed", evidence=self._evidence(), detail="upload not finished")
        pause()
        stop = self._stop_unless(PageState.COMPOSER_OPEN.value, PageState.READY.value)
        if stop:
            return stop

        self.b.click(LOCATORS["caption"])
        self.b.press("Control+A")  # the editor may hold the file name
        self.b.keyboard_type(self.text)
        pause()
        if first_line(self.text) not in self.b.evaluate(CAPTION_TEXT)["result"]:
            snapshot = self.b.snapshot(interactive_only=True)["snapshot"]
            return self._end("needs_agent", detail="caption was not entered", snapshot=snapshot)
        if visibility == "only_me":
            for key in ("visibility_button", "visibility_only_me"):
                self.b.click(LOCATORS[key])
                pause()

        if dry_run:
            evidence = self._evidence()
            self.b.click(LOCATORS["discard_button"])
            self.b.click(LOCATORS["discard_confirm"])
            return self._end("dry_run", evidence=evidence, detail="stopped before Post")

        self.click_post(LOCATORS["post_button"])
        # Success leaves the upload page for the post list. A dialog instead (content check,
        # copyright...) needs a human: never press anything in it.
        for _ in range(PUBLISH_SECONDS):
            _sleep(1)
            if LOCATORS["posts_list_url"] in self.b.evaluate("location.href")["result"]:
                break
            modal = self.b.evaluate(MODAL_TEXT)["result"]
            if modal:
                return self.sent(
                    "failed",
                    evidence=self._evidence(),
                    detail=f"publish unconfirmed: dialog {modal}",
                )
        else:
            return self.sent("failed", evidence=self._evidence(), detail="publish unconfirmed")

        find = FIND_POST_URL % json.dumps(first_line(self.text))
        url = ""
        for _ in range(LIST_ATTEMPTS):  # a new post may take a moment to appear in the list
            self.b.navigate("https://www.tiktok.com" + LOCATORS["posts_list_url"])
            _sleep(5)
            url = self.b.evaluate(find)["result"] or ""
            if url:
                break
        return self.confirm_safe(url)
