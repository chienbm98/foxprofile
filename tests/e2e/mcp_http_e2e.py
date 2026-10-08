"""Drive FoxProfile's MCP endpoint over Streamable HTTP, as Claude Code / Cursor would."""

import asyncio
import base64
import os
import time
import urllib.error
import urllib.request

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = os.getenv("FOXPROFILE_URL", "http://127.0.0.1:8000").rstrip("/") + "/mcp"
TOKEN = os.environ.get("FOXPROFILE_API_TOKEN", "")
results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{str(detail)[:140]}]" if detail else ""))


for _ in range(60):
    try:
        urllib.request.urlopen(
            os.getenv("FOXPROFILE_URL", "http://127.0.0.1:8000").rstrip("/") + "/api/v1/health",
            timeout=2,
        )
        break
    except Exception:
        time.sleep(1)

req = urllib.request.Request(
    URL, data=b"{}", method="POST", headers={"Content-Type": "application/json"}
)
try:
    urllib.request.urlopen(req, timeout=10)
    check("/mcp without token -> 401", False)
except urllib.error.HTTPError as e:
    check("/mcp without token -> 401", e.code == 401, e.code)


def text(r):
    return "".join(c.text for c in r.content if getattr(c, "type", "") == "text")


async def main():
    headers = {"Authorization": f"Bearer {TOKEN}"}
    async with (
        streamablehttp_client(URL, headers=headers) as (read, write, _),
        ClientSession(read, write) as s,
    ):
        init = await s.initialize()
        check("initialize over HTTP", init.serverInfo.name == "foxprofile")
        tools = (await s.list_tools()).tools
        check("27 tools over HTTP", len(tools) == 27, len(tools))

        async def call(tool, **args):
            r = await s.call_tool(tool, args)
            return r, text(r)

        await call("stop_profile", name="http-demo")
        await call("create_profile", name="http-demo", os_type="windows")
        t0 = time.time()
        r, txt = await call("launch_profile", name="http-demo")
        check(
            "launch_profile (tool calls back into same server, no deadlock)",
            not r.isError,
            f"{txt[:60]} {time.time() - t0:.1f}s",
        )
        r, txt = await call("browser_navigate", profile="http-demo", url="https://example.com")
        check("browser_navigate", "Example Domain" in txt, txt)
        r, _ = await call("browser_screenshot", profile="http-demo")
        img = [c for c in r.content if c.type == "image"]
        check("browser_screenshot image", img and base64.b64decode(img[0].data)[:4] == b"\x89PNG")
        r, txt = await call("stop_profile", name="http-demo")
        check("stop_profile", not r.isError, txt[:60])


asyncio.run(main())
print(f"\n{sum(results)}/{len(results)} checks passed")
