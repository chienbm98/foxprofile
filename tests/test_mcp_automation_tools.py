"""The MCP server exposes the posting macros and read-only views, and nothing that lifts a guard."""

import asyncio

from src.mcp_server import server
from tqd_automation.platforms import facebook, tiktok, x
from tqd_automation.result import PostResult

AUTOMATION_TOOLS = {"post_facebook", "post_tiktok", "post_x", "automation_status", "page_state"}


def tool_names():
    return {t.name for t in asyncio.run(server.mcp.list_tools())}


def test_automation_tools_are_listed():
    assert tool_names() >= AUTOMATION_TOOLS


def test_no_tool_lifts_a_guard_or_deletes():
    assert not [n for n in tool_names() if any(w in n for w in ("delete", "unlock", "kill"))]


def test_post_tools_pass_their_arguments_and_return_the_result(monkeypatch):
    seen = {}

    def fake(name):
        def post(*args):
            seen[name] = args
            return PostResult("dry_run", evidence="e.png")

        return post

    for module in (facebook, tiktok, x):
        monkeypatch.setattr(module, "post", fake(module.PLATFORM))

    def call(tool, args):
        return asyncio.run(server.mcp.call_tool(tool, args))

    call("post_facebook", {"profile": "fb", "text": "Xin chào", "dry_run": True})
    call("post_tiktok", {"profile": "tt", "caption": "Chào", "media": ["media_outbox/a.png"]})
    call("post_x", {"profile": "xm", "text": "Hi", "media": ["media_outbox/a.png"]})
    assert seen == {
        "facebook": ("fb", "Xin chào", [], "default", True),
        "tiktok": ("tt", "Chào", ["media_outbox/a.png"], "default", False),
        "x": ("xm", "Hi", ["media_outbox/a.png"], False),
    }
    assert asyncio.run(server.post_facebook("fb", "Xin chào")) == {
        "status": "dry_run",
        "url": "",
        "evidence": "e.png",
        "detail": "",
        "snapshot": "",
    }
