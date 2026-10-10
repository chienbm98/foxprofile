"""The Judge reads page state and gates post text; both verdicts are logged side by side."""

import json

import pytest

from tqd_automation.judge import (
    CompositeJudge,
    HeuristicJudge,
    PageState,
    Verdict,
    make_judge,
)

LOGIN_PAGE = '- heading "Facebook"\n- textbox "Email or phone number"\n- textbox "Password"\n- button "Log in"'
LOGIN_PAGE_VI = '- textbox "Email hoặc số điện thoại"\n- textbox "Mật khẩu"\n- button "Đăng nhập"'
FEED_PAGE = '- navigation "Facebook"\n- button "What\'s on your mind, Dung?"\n- link "Home"'


@pytest.fixture(autouse=True)
def _in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TQD_AUTOMATION_DIR", str(tmp_path / "automation_data"))
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)


class FakeJudge:
    """Stands in for the TypeSafe judge with fixed answers."""

    def __init__(self, page: Verdict, content: Verdict | None = None):
        self.page, self.content = page, content

    def page_state(self, platform, url, snapshot):
        return self.page

    def content_ok(self, platform, text):
        return self.content


def test_checkpoint_url_is_a_checkpoint():
    v = HeuristicJudge().page_state("facebook", "https://www.facebook.com/checkpoint/1501", "")
    assert v.label == PageState.CHECKPOINT
    assert v.source == "heuristic"


@pytest.mark.parametrize(
    "phrase", ["Please solve this CAPTCHA", "Security check", "Kiểm tra bảo mật"]
)
def test_captcha_phrases(phrase):
    v = HeuristicJudge().page_state(
        "facebook", "https://www.facebook.com/", f"- heading {phrase!r}"
    )
    assert v.label == PageState.CAPTCHA


@pytest.mark.parametrize("snapshot", [LOGIN_PAGE, LOGIN_PAGE_VI])
def test_login_form_is_logged_out(snapshot):
    v = HeuristicJudge().page_state("facebook", "https://www.facebook.com/", snapshot)
    assert v.label == PageState.LOGGED_OUT


def test_log_in_link_without_password_box_is_not_logged_out():
    snapshot = FEED_PAGE + '\n- link "Log in with another account"'
    v = HeuristicJudge().page_state("facebook", "https://www.facebook.com/", snapshot)
    assert v.label == PageState.READY


def test_feed_is_ready():
    v = HeuristicJudge().page_state("facebook", "https://www.facebook.com/", FEED_PAGE)
    assert v.label == PageState.READY


def test_blank_page_is_unknown():
    v = HeuristicJudge().page_state("facebook", "about:blank", "")
    assert v.label == PageState.UNKNOWN


@pytest.mark.parametrize(
    ("platform", "text", "label"),
    [
        ("facebook", "Chào buổi sáng", "ok"),
        ("facebook", "   ", "block"),
        ("facebook", "x" * 5001, "block"),
        ("tiktok", "x" * 2200, "ok"),
        ("tiktok", "x" * 2201, "block"),
    ],
)
def test_content_limits(platform, text, label):
    assert HeuristicJudge().content_ok(platform, text).label == label


def test_blocked_phrase_file(tmp_path):
    (tmp_path / "automation_data").mkdir()
    (tmp_path / "automation_data" / "blocked_phrases.txt").write_text(
        "kiếm tiền nhanh\n\n", encoding="utf-8"
    )
    v = HeuristicJudge().content_ok("facebook", "Bí quyết KIẾM TIỀN NHANH mỗi ngày")
    assert v.label == "block"
    assert "kiếm tiền nhanh" in v.detail
    assert HeuristicJudge().content_ok("facebook", "Một ngày bình thường").label == "ok"


def _log_lines(tmp_path):
    files = list((tmp_path / "automation_data").glob("judge_*.jsonl"))
    assert len(files) == 1
    return [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]


def test_hard_signal_from_heuristic_beats_confident_typesafe():
    ts = FakeJudge(Verdict("READY", 0.99, "typesafe"))
    v = CompositeJudge(HeuristicJudge(), ts).page_state(
        "facebook", "https://www.facebook.com/checkpoint/1", ""
    )
    assert v.label == PageState.CHECKPOINT


def test_logged_out_is_a_hard_signal():
    ts = FakeJudge(Verdict("READY", 0.95, "typesafe"))
    v = CompositeJudge(HeuristicJudge(), ts).page_state(
        "facebook", "https://www.facebook.com/", LOGIN_PAGE
    )
    assert v.label == PageState.LOGGED_OUT


def test_hard_signal_from_typesafe_wins():
    ts = FakeJudge(Verdict("CAPTCHA", 0.4, "typesafe"))
    v = CompositeJudge(HeuristicJudge(), ts).page_state(
        "facebook", "https://www.facebook.com/", FEED_PAGE
    )
    assert v.label == PageState.CAPTCHA


def test_confident_typesafe_label_wins():
    ts = FakeJudge(Verdict("COMPOSER_OPEN", 0.9, "typesafe"))
    v = CompositeJudge(HeuristicJudge(), ts).page_state(
        "facebook", "https://www.facebook.com/", FEED_PAGE
    )
    assert v.label == PageState.COMPOSER_OPEN
    assert v.source == "typesafe"


def test_unsure_typesafe_falls_back_to_heuristic():
    ts = FakeJudge(Verdict("COMPOSER_OPEN", 0.5, "typesafe"))
    v = CompositeJudge(HeuristicJudge(), ts).page_state(
        "facebook", "https://www.facebook.com/", FEED_PAGE
    )
    assert v.label == PageState.READY


def test_content_blocks_when_either_blocks():
    ts = FakeJudge(Verdict("READY", 1, "typesafe"), Verdict("block", 0.2, "typesafe", "spam"))
    judge = CompositeJudge(HeuristicJudge(), ts)
    assert judge.content_ok("facebook", "Mua ngay!!!").label == "block"
    ts.content = Verdict("ok", 0.9, "typesafe")
    assert judge.content_ok("facebook", "Mua ngay!!!").label == "ok"
    assert judge.content_ok("facebook", "").label == "block"


def test_every_call_logs_both_verdicts(tmp_path):
    ts = FakeJudge(Verdict("READY", 0.9, "typesafe"), Verdict("ok", 0.9, "typesafe"))
    judge = CompositeJudge(HeuristicJudge(), ts)
    judge.page_state("facebook", "https://www.facebook.com/", FEED_PAGE)
    judge.content_ok("facebook", "Xin chào")
    lines = _log_lines(tmp_path)
    assert [line["kind"] for line in lines] == ["page_state", "content"]
    for line in lines:
        assert line["heuristic"]["source"] == "heuristic"
        assert line["typesafe"]["source"] == "typesafe"
        assert line["final"]["label"]
    assert "Xin chào" not in json.dumps(lines, ensure_ascii=False)


def test_log_without_typesafe(tmp_path):
    judge = CompositeJudge(HeuristicJudge())
    judge.page_state("tiktok", "https://www.tiktok.com/", "")
    assert _log_lines(tmp_path)[0]["typesafe"] is None


def test_make_judge_without_key_has_no_typesafe():
    assert make_judge().typesafe is None


class FakeTypeSafeClient:
    def __init__(self, answers=None, error=None):
        self.answers, self.error, self.calls = answers, error, []

    def system_one(self, state, questions):
        self.calls.append((state, questions))
        if self.error:
            raise self.error
        return type("Result", (), {"answers": self.answers})()


def _answer(**fields):
    return type("Answer", (), fields)()


def test_typesafe_judge_reads_choice_and_noul():
    pytest.importorskip("typesafe_sdk")
    from tqd_automation.judge import TypeSafeJudge

    client = FakeTypeSafeClient({"page_state": _answer(choice="READY", confidence=0.87)})
    v = TypeSafeJudge(client).page_state("facebook", "https://www.facebook.com/", "x" * 9000)
    assert (v.label, v.confidence, v.source) == ("READY", 0.87, "typesafe")
    state, questions = client.calls[0]
    assert len(state["snapshot"]) == 8000
    assert set(questions["page_state"].criteria) == {s.value for s in PageState}

    client.answers = {"safe": _answer(noul=0.65)}
    assert TypeSafeJudge(client).content_ok("facebook", "hi").label == "block"
    client.answers = {"safe": _answer(noul=0.95)}
    assert TypeSafeJudge(client).content_ok("facebook", "hi").label == "ok"


def test_typesafe_errors_become_unknown():
    pytest.importorskip("typesafe_sdk")
    from tqd_automation.judge import TypeSafeJudge

    client = FakeTypeSafeClient(error=RuntimeError("quota exceeded"))
    v = TypeSafeJudge(client).page_state("facebook", "https://www.facebook.com/", "")
    assert (v.label, v.confidence) == ("UNKNOWN", 0.0)
    assert "quota" in v.detail
    assert TypeSafeJudge(client).content_ok("facebook", "hi").label == "UNKNOWN"
