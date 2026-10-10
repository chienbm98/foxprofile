"""Steps every posting macro shares: locking, gates, page-state stops, evidence and the ledger.

A platform subclasses `BaseRun`, sets `platform` and implements `act()` (open the composer, fill it,
then `dry_run` or `click_post()` and confirm). `run_macro` wraps it in the run lock and turns a
failed page step into a `failed` result, never a retry.
"""

from __future__ import annotations

import json
import time
from functools import partial
from typing import Any

from src.mcp_server.server import FoxProfileError

from .. import data_dir
from ..guards import GuardBusy, Guards
from ..judge import PageState, make_judge
from ..result import PostResult

HARD_STOPS = (PageState.CHECKPOINT.value, PageState.CAPTCHA.value)


def first_line(text: str, limit: int = 40) -> str:
    """The start of the post text, used to find the post again after publishing."""
    return text.strip().splitlines()[0][:limit]


class BaseRun:
    platform = ""

    def __init__(self, profile: str, text: str, media: list[str], browser, judge, guards: Guards):
        self.profile, self.text, self.media = profile, text, media
        self.b, self.judge, self.guards = browser, judge, guards
        self.clicked = False
        self.record = partial(
            guards.record,
            attempt_id=guards.new_attempt(),
            platform=self.platform,
            profile=profile,
            text=text,
        )

    def validate(self) -> str | None:
        """A reason the media cannot be posted on this platform, checked before anything else."""
        return None

    def go(self, visibility: str, dry_run: bool) -> PostResult:
        problem = self.validate()
        if problem:
            return self._end("failed", detail=problem)
        reason = self.guards.check(self.platform, self.profile, self.text)
        if reason:
            return self._end("blocked", detail=reason)
        verdict = self.judge.content_ok(self.platform, self.text)
        if verdict.label == "block":
            return self._end("blocked", detail=f"content blocked: {verdict.detail}")
        if self.guards.require_approval():
            return self._draft(visibility)
        self.b.ensure_running()
        return self.act(visibility, dry_run)

    def act(self, visibility: str, dry_run: bool) -> PostResult:
        raise NotImplementedError

    def click_post(self, selector: str) -> None:
        """Write the pending line first, so a crash after the click still counts as sent."""
        self.record(status="pending", post_clicked=True)
        self.clicked = True
        self.b.click(selector)

    def sent(self, status: str, **kw: Any) -> PostResult:
        return self._end(status, post_clicked=True, **kw)

    def confirm_safe(self, url: str) -> PostResult:
        """Last check after publishing: a checkpoint now still locks the account out."""
        state, _ = self._look()
        if state.label in HARD_STOPS:
            self.guards.lockout(self.platform, self.profile, f"{state.label} after publishing")
            return self.sent(
                "blocked", evidence=self._evidence(), detail=f"{state.label} after publish"
            )
        detail = "" if url else "post published but its link was not found yet"
        return self.sent("published", url=url, evidence=self._evidence(), detail=detail)

    def _look(self):
        url = self.b.evaluate("location.href")["result"]
        snapshot = self.b.snapshot()["snapshot"]
        return self.judge.page_state(self.platform, url, snapshot), url

    def _stop_unless(self, *allowed: str) -> PostResult | None:
        state, url = self._look()
        if state.label in HARD_STOPS:
            self.guards.lockout(self.platform, self.profile, f"{state.label} page at {url}")
            return self._end("blocked", evidence=self._evidence(), detail=f"{state.label} page")
        if state.label == PageState.LOGGED_OUT.value:
            return self._end("failed", detail="logged out: log in manually in the profile")
        if state.label not in allowed:
            snapshot = self.b.snapshot(interactive_only=True)["snapshot"]
            return self._end(
                "needs_agent", detail=f"unexpected page state {state.label}", snapshot=snapshot
            )
        return None

    def _evidence(self) -> str:
        return self.guards.save_evidence(self.b.screenshot_png(), self.platform, self.profile)

    def _draft(self, visibility: str) -> PostResult:
        folder = data_dir() / "drafts"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{self.platform}-{time.strftime('%Y%m%d-%H%M%S')}.json"
        draft = {"profile": self.profile, "text": self.text, "media": self.media}
        path.write_text(
            json.dumps({**draft, "visibility": visibility}, ensure_ascii=False), "utf-8"
        )
        return self._end("awaiting_approval", detail=f"draft saved to {path.as_posix()}")

    def _end(
        self,
        status: str,
        *,
        post_clicked: bool = False,
        url: str = "",
        evidence: str = "",
        detail: str = "",
        snapshot: str = "",
    ) -> PostResult:
        self.record(
            status=status, post_clicked=post_clicked, url=url, evidence=evidence, detail=detail
        )
        return PostResult(status, url=url, evidence=evidence, detail=detail, snapshot=snapshot)


def run_macro(
    run_cls: type[BaseRun],
    profile: str,
    text: str,
    media: list[str] | None,
    visibility: str,
    dry_run: bool,
    browser: Any = None,
    judge: Any = None,
    guards: Guards | None = None,
) -> PostResult:
    if browser is None:
        from ..client import Browser

        browser = Browser(profile)
    judge = judge or make_judge()
    guards = guards or Guards()
    try:
        with guards.run_lock(run_cls.platform, profile):
            run = run_cls(profile, text, media or [], browser, judge, guards)
            try:
                return run.go(visibility, dry_run)
            except FoxProfileError as e:  # a page step failed: report it, never retry the click
                return run._end("failed", post_clicked=run.clicked, detail=str(e)[:300])
    except GuardBusy as e:
        return PostResult("blocked", detail=str(e))
