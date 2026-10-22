"""Sign a profile back in to Gmail with the stored credentials.

A small state machine drives Google's own sign-in pages through the profile's page
control: it types like a person (random pauses, one key at a time), and stops on
anything it does not recognise (phone prompt, "is it you", CAPTCHA) so the account is
never hammered. Secrets are passed in by the caller and never logged or returned.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Any

from . import session_check

SIGN_IN_URL = (
    "https://accounts.google.com/ServiceLogin?service=mail"
    "&continue=https%3A%2F%2Fmail.google.com%2Fmail%2Fu%2F0%2F"
)

PROBE = """() => {
  const q = (s) => document.querySelector(s);
  const shown = (e) => !!e && e.getClientRects().length > 0;
  const path = location.pathname;
  let step = "unknown";
  if (shown(q("input[name=totpPin], input#totpPin"))) step = "totp";
  else if (shown(q("input[type=password]"))) step = "password";
  else if (shown(q("input#identifierId, input[type=email][name=identifier]"))) step = "email";
  else if (path.includes("/challenge")) step = "challenge";
  else if (document.querySelector("[data-identifier]")) step = "chooser";
  return {
    step, url: location.href, title: document.title,
    accounts: [...document.querySelectorAll("[data-identifier]")]
      .map((e) => e.getAttribute("data-identifier")),
  };
}"""

Control = Callable[..., Any]


def _pause(lo: float, hi: float, sleep: Callable[[float], None]) -> None:
    sleep(random.uniform(lo, hi))


def type_like_a_person(
    control: Control,
    name: str,
    selector: str,
    text: str,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    control(name, "click", {"selector": selector})
    _pause(0.3, 0.8, sleep)
    for ch in text:
        control(name, "keyboard_type", {"text": ch})
        _pause(0.05, 0.22, sleep)
    _pause(0.4, 1.0, sleep)


def sign_in(
    control: Control,
    name: str,
    email: str,
    password: str | None,
    totp_code: Callable[[], str] | None,
    mode: str = "full",
    sleep: Callable[[float], None] = time.sleep,
    settle: float = 3.0,
    max_steps: int = 14,
    url: str = SIGN_IN_URL,
) -> dict[str, Any]:
    """Result: state is logged_in, needs_verification or failed; `detail` says why."""
    if mode == "manual":
        return {"state": "failed", "detail": "this account is set to manual login"}
    if not email:
        return {"state": "failed", "detail": "no email stored for this profile"}
    if mode == "full" and not password:
        return {"state": "failed", "detail": "no password stored for this profile"}

    control(name, "navigate", {"url": url})
    done: set[str] = set()
    info: dict[str, Any] = {}
    for _ in range(max_steps):
        sleep(settle)
        info = control(name, "evaluate", {"script": PROBE})["result"]
        step = info["step"]
        if session_check.classify(info["url"], info["title"])["state"] == "alive":
            return {"state": "logged_in", "detail": "inbox reached"}
        if step in done and step != "chooser":
            return {
                "state": "needs_verification",
                "detail": f"the {step} step came back after it was filled in "
                "(wrong value or an extra check)",
            }
        if step == "chooser":
            match = next((a for a in info["accounts"] if a.lower() == email.lower()), None)
            if match is None or "chooser" in done:
                return {"state": "needs_verification", "detail": "account not in the chooser"}
            control(name, "click", {"selector": f'[data-identifier="{match}"]'})
            done.add("chooser")
        elif step == "email":
            type_like_a_person(control, name, "input[type=email], input#identifierId", email, sleep)
            control(name, "press", {"key": "Enter"})
            done.add("email")
            if mode == "email_only":
                return {"state": "needs_verification", "detail": "email filled, finish by hand"}
        elif step == "password":
            if not password:
                return {"state": "needs_verification", "detail": "password step, none stored"}
            type_like_a_person(control, name, "input[type=password]", password, sleep)
            control(name, "press", {"key": "Enter"})
            done.add("password")
        elif step == "totp":
            if totp_code is None:
                return {
                    "state": "needs_verification",
                    "detail": "2-step code needed, no key stored",
                }
            type_like_a_person(
                control, name, "input[name=totpPin], input#totpPin", totp_code(), sleep
            )
            control(name, "press", {"key": "Enter"})
            done.add("totp")
        elif step == "challenge":
            return {"state": "needs_verification", "detail": "Google asked for another check"}
        else:
            return {
                "state": "needs_verification",
                "detail": f"unrecognised page ({info['url'][:60]})",
            }
    return {"state": "needs_verification", "detail": "sign-in did not finish in time"}
