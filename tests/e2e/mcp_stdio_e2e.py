"""End-to-end: HTTP auth checks, then drive FoxProfile through a real MCP stdio client."""

import asyncio
import base64
import json
import os
import pathlib
import time
import urllib.error
import urllib.request

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BASE = os.getenv("FOXPROFILE_URL", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.environ.get("FOXPROFILE_API_TOKEN", "")
ROOT = str(pathlib.Path(__file__).resolve().parents[2])
results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{str(detail)[:150]}]" if detail else ""))


def http(path, token=None, method="GET"):
    req = urllib.request.Request(BASE + path, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


for _ in range(60):
    try:
        if http("/api/v1/health")[0] == 200:
            break
    except Exception:
        time.sleep(1)

s, b = http("/api/v1/info")
check(
    "info is public and says auth is required",
    s == 200 and json.loads(b)["auth_required"] is True,
    b,
)
check("health is public", http("/api/v1/health")[0] == 200)
check("panel served at /", http("/")[0] == 200 and b"FoxProfile" in http("/")[1])
check("profiles without token -> 401", http("/api/v1/profiles")[0] == 401)
check("profiles with wrong token -> 401", http("/api/v1/profiles", "x" * 30)[0] == 401)
check("profiles with token -> 200", http("/api/v1/profiles", TOKEN)[0] == 200)
check("page control without token -> 401", http("/api/v1/browser/x/page/tabs")[0] == 401)


def text_of(result):
    return "".join(c.text for c in result.content if getattr(c, "type", "") == "text")


async def main():
    params = StdioServerParameters(
        command=os.path.join(ROOT, ".venv", "Scripts", "python.exe"),
        args=["-m", "src.mcp_server"],
        cwd=ROOT,
        env={**os.environ, "FOXPROFILE_URL": BASE, "FOXPROFILE_API_TOKEN": TOKEN},
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        init = await session.initialize()
        check("MCP initialize", init.serverInfo.name == "foxprofile", init.serverInfo)
        tools = (await session.list_tools()).tools
        check("MCP lists 27 tools", len(tools) == 27, len(tools))

        async def call(tool, **args):
            r = await session.call_tool(tool, args)
            return r, text_of(r)

        await call("stop_profile", name="mcp-demo")
        r, txt = await call("create_profile", name="mcp-demo", os_type="macos")
        check("create_profile", not r.isError and "mcp-demo" in txt, txt)
        r, txt = await call("create_profile", name="..", os_type="windows")
        check("create_profile rejects '..'", r.isError, txt)
        t0 = time.time()
        r, txt = await call("launch_profile", name="mcp-demo")
        check(
            "launch_profile", not r.isError and "started" in txt, f"{txt} {time.time() - t0:.1f}s"
        )
        r, txt = await call("browser_navigate", profile="mcp-demo", url="https://example.com")
        check("browser_navigate", "Example Domain" in txt, txt)
        r, txt = await call("browser_snapshot", profile="mcp-demo")
        check("browser_snapshot has link", "link" in txt and "Learn more" in txt, txt[:160])
        r, txt = await call("browser_click", profile="mcp-demo", selector="role=link")
        check("browser_click follows link", "iana.org" in txt, txt)
        r, txt = await call("browser_evaluate", profile="mcp-demo", script="navigator.platform")
        check("evaluate shows macOS platform", "MacIntel" in txt, txt)
        r, _ = await call("browser_screenshot", profile="mcp-demo")
        img = [c for c in r.content if c.type == "image"]
        check(
            "browser_screenshot returns PNG image",
            img and base64.b64decode(img[0].data)[:4] == b"\x89PNG",
            img and img[0].mimeType,
        )
        r, txt = await call(
            "browser_navigate", profile="mcp-demo", url="file:///C:/Windows/win.ini"
        )
        check("file:// navigation refused", r.isError and "not allowed" in txt, txt)
        r, txt = await call("browser_tab_new", profile="mcp-demo", url="https://example.org")
        check(
            "browser_tab_new",
            '"index": 1' in txt or "'index': 1" in txt or "example.org" in txt,
            txt[:120],
        )
        r, txt = await call("import_cookies", name="mcp-demo", content="[]")
        check("cookie import blocked while running", r.isError and "Stop the browser" in txt, txt)
        r, txt = await call("stop_profile", name="mcp-demo")
        check("stop_profile", not r.isError, txt)
        r, txt = await call("browser_snapshot", profile="mcp-demo")
        check("page control after stop -> error", r.isError and "not running" in txt, txt)
        cookie = json.dumps(
            [
                {
                    "domain": ".example.com",
                    "name": "mcp",
                    "value": "1",
                    "path": "/",
                    "expirationDate": time.time() + 86400,
                }
            ]
        )
        r, txt = await call("import_cookies", name="mcp-demo", content=cookie)
        check("import_cookies when stopped", '"imported": 1' in txt or "imported" in txt, txt)
        r, txt = await call("export_cookies", name="mcp-demo", format="netscape")
        check("export_cookies netscape", "\tmcp\t1" in txt, txt[:120])
        r, txt = await call("get_fingerprint", name="mcp-demo")
        check("get_fingerprint", "MacIntel" in txt, txt)


asyncio.run(main())
print(f"\n{sum(results)}/{len(results)} checks passed")
