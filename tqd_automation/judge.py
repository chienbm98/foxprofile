"""Decide what a page is showing and whether a post text may be published.

The heuristic judge always runs. The TypeSafe judge runs too when `TYPESAFE_API_KEY` is set and the
`typesafe-sdk` package is installed. Every decision is logged with both verdicts so they can be compared.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

from . import data_dir, rules

TYPESAFE_TRUSTED = 0.8
TYPESAFE_SAFE = 0.7
SNAPSHOT_LIMIT = 8000


class PageState(str, Enum):
    LOGGED_OUT = "LOGGED_OUT"
    CHECKPOINT = "CHECKPOINT"
    CAPTCHA = "CAPTCHA"
    READY = "READY"
    COMPOSER_OPEN = "COMPOSER_OPEN"
    PUBLISHED = "PUBLISHED"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"


# Labels that stop a macro, whichever judge reports them and however unsure it is.
HARD_SIGNALS = (PageState.CHECKPOINT, PageState.CAPTCHA, PageState.LOGGED_OUT)

PAGE_STATE_CRITERIA = {
    PageState.LOGGED_OUT: "A login form is shown; the account is not signed in.",
    PageState.CHECKPOINT: "The platform has locked or is verifying the account (checkpoint, confirm identity).",
    PageState.CAPTCHA: "A captcha, puzzle or security check must be solved.",
    PageState.READY: "Signed in on a normal page where a new post can be started.",
    PageState.COMPOSER_OPEN: "The post composer or upload form is open.",
    PageState.PUBLISHED: "The page confirms that a post was just published.",
    PageState.ERROR: "An error page or error message blocks the task.",
    PageState.UNKNOWN: "None of the above can be told from the page.",
}

CONTENT_QUESTION = (
    "Is this post safe to publish on a personal account: no hate, no harassment, no false "
    "medical/financial claims, no personal data of others, no spam?"
)


@dataclass
class Verdict:
    label: str
    confidence: float
    source: str
    detail: str = ""


class Judge(Protocol):
    def page_state(self, platform: str, url: str, snapshot: str) -> Verdict: ...

    def content_ok(self, platform: str, text: str) -> Verdict: ...


def _has(haystack: str, needles: tuple[str, ...]) -> bool:
    return any(n in haystack for n in needles)


class HeuristicJudge:
    def page_state(self, platform: str, url: str, snapshot: str) -> Verdict:
        url, page = url.lower(), snapshot.lower()
        signals = rules.PLATFORMS.get(platform, {})
        checks = [
            (PageState.CHECKPOINT, _has(url, rules.CHECKPOINT_URLS)),
            (PageState.CAPTCHA, _has(page, rules.CAPTCHA_PHRASES)),
            (
                PageState.LOGGED_OUT,
                _has(url, rules.LOGIN_URLS)
                or (_has(page, rules.LOGIN_PHRASES) and _has(page, rules.PASSWORD_PHRASES)),
            ),
            (PageState.PUBLISHED, _has(page, signals.get("published", ()))),
            (PageState.COMPOSER_OPEN, _has(page, signals.get("composer", ()))),
            (PageState.READY, _has(page, signals.get("ready", ()))),
        ]
        for state, matched in checks:
            if matched:
                confidence = 0.95 if state in HARD_SIGNALS else 0.6
                return Verdict(state.value, confidence, "heuristic")
        return Verdict(PageState.UNKNOWN.value, 0.0, "heuristic")

    def content_ok(self, platform: str, text: str) -> Verdict:
        if not text.strip():
            return Verdict("block", 1.0, "heuristic", "empty text")
        signals = rules.PLATFORMS.get(platform, {})
        limit = signals.get("max_chars", 2200)
        length = weighted_length(text) if signals.get("weighted") else len(text)
        if length > limit:
            return Verdict("block", 1.0, "heuristic", f"text longer than {limit} characters")
        lowered = text.lower()
        for phrase in _blocked_phrases():
            if phrase in lowered:
                return Verdict("block", 1.0, "heuristic", f"blocked phrase: {phrase}")
        return Verdict("ok", 1.0, "heuristic")


# twitter-text v3: these code point ranges count 1, everything else 2; every URL counts 23.
_LIGHT_RANGES = ((0, 4351), (8192, 8205), (8208, 8223), (8242, 8247))
_URL = re.compile(r"https?://\S+")


def weighted_length(text: str) -> int:
    text = unicodedata.normalize("NFC", text)
    urls = _URL.findall(text)
    rest = _URL.sub("", text)
    light = sum(1 for ch in rest if any(lo <= ord(ch) <= hi for lo, hi in _LIGHT_RANGES))
    return 23 * len(urls) + light + 2 * (len(rest) - light)


def _blocked_phrases() -> list[str]:
    path = data_dir() / "blocked_phrases.txt"
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip().lower() for line in lines if line.strip()]


class TypeSafeJudge:
    def __init__(self, client: Any):
        self.client = client

    @classmethod
    def from_env(cls) -> TypeSafeJudge | None:
        key = os.getenv("TYPESAFE_API_KEY")
        if not key:
            return None
        try:
            from typesafe_sdk import TypeSafeClient
        except ImportError:
            return None
        return cls(TypeSafeClient(api_key=key, model=os.getenv("TYPESAFE_MODEL") or None))

    def page_state(self, platform: str, url: str, snapshot: str) -> Verdict:
        from typesafe_sdk import Choice

        state = {"platform": platform, "url": url, "snapshot": snapshot[:SNAPSHOT_LIMIT]}
        question = Choice(
            instructions="Which state is this browser page in?",
            criteria={s.value: d for s, d in PAGE_STATE_CRITERIA.items()},
        )
        try:
            answer = self.client.system_one(state, {"page_state": question}).answers["page_state"]
            return Verdict(answer.choice, float(answer.confidence), "typesafe")
        except Exception as e:  # the judge must never crash a macro
            return Verdict(PageState.UNKNOWN.value, 0.0, "typesafe", str(e)[:200])

    def content_ok(self, platform: str, text: str) -> Verdict:
        from typesafe_sdk import Noul

        try:
            answer = self.client.system_one(
                {"platform": platform, "text": text},
                {"safe": Noul(instructions=CONTENT_QUESTION)},
            ).answers["safe"]
            score = float(answer.noul)
        except Exception as e:  # the heuristic still gates content when TypeSafe is down
            return Verdict(PageState.UNKNOWN.value, 0.0, "typesafe", str(e)[:200])
        label = "ok" if score >= TYPESAFE_SAFE else "block"
        return Verdict(label, score, "typesafe")


class CompositeJudge:
    def __init__(self, heuristic: Judge, typesafe: Judge | None = None):
        self.heuristic = heuristic
        self.typesafe = typesafe

    def page_state(self, platform: str, url: str, snapshot: str) -> Verdict:
        h = self.heuristic.page_state(platform, url, snapshot)
        t = self.typesafe.page_state(platform, url, snapshot) if self.typesafe else None
        final = self._decide_page(h, t)
        self._log("page_state", platform, {"url": url}, h, t, final)
        return final

    def content_ok(self, platform: str, text: str) -> Verdict:
        h = self.heuristic.content_ok(platform, text)
        t = self.typesafe.content_ok(platform, text) if self.typesafe else None
        final = t if h.label != "block" and t and t.label == "block" else h
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        self._log("content", platform, {"text_sha256": digest, "chars": len(text)}, h, t, final)
        return final

    @staticmethod
    def _decide_page(h: Verdict, t: Verdict | None) -> Verdict:
        for state in HARD_SIGNALS:
            for verdict in (h, t):
                if verdict and verdict.label == state.value:
                    return verdict
        if t and t.confidence >= TYPESAFE_TRUSTED:
            return t
        return h

    @staticmethod
    def _log(kind: str, platform: str, extra: dict, h: Verdict, t: Verdict | None, final: Verdict):
        now = datetime.now().astimezone()
        line = {
            "ts": now.isoformat(timespec="seconds"),
            "kind": kind,
            "platform": platform,
            **extra,
            "heuristic": asdict(h),
            "typesafe": asdict(t) if t else None,
            "final": asdict(final),
        }
        path = data_dir() / f"judge_{now:%Y%m%d}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


def make_judge() -> CompositeJudge:
    return CompositeJudge(HeuristicJudge(), TypeSafeJudge.from_env())
