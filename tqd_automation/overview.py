"""Read-only views shared by the CLI and the MCP tools."""

from __future__ import annotations

from dataclasses import asdict

from . import client
from .guards import Guards
from .judge import make_judge


def automation_status(guards: Guards | None = None) -> list[dict]:
    """Caps, waits, lockouts and recent ledger lines for every account that has posted."""
    g = guards or Guards()
    return [g.status(platform, profile) for platform, profile in g.accounts()]


def page_state(profile: str, platform: str) -> dict:
    """The judge's verdict on the page currently open in the profile, plus its URL."""
    browser = client.Browser(profile)
    url = browser.evaluate("location.href")["result"]
    snapshot = browser.snapshot()["snapshot"]
    verdict = make_judge().page_state(platform, url, snapshot)
    return {**asdict(verdict), "url": url}
