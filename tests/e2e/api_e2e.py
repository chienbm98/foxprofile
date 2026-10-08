"""End-to-end checks against a running FoxProfile API."""

import hashlib
import json
import os
import pathlib
import time
import urllib.error
import urllib.request

BASE = os.getenv("FOXPROFILE_URL", "http://127.0.0.1:8000").rstrip("/") + "/api/v1"
DATA = pathlib.Path(os.getenv("FOXPROFILE_DATA_DIR", "camoufox_data"))
TOKEN = os.getenv("FOXPROFILE_API_TOKEN", "")
HEADERS = {
    "Content-Type": "application/json",
    **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
}
results = []


def call(method, path, body=None, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            text = r.read().decode("utf-8")
            return r.status, (text if raw else json.loads(text)), dict(r.headers)
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8")
        try:
            return e.code, json.loads(text), {}
        except ValueError:
            return e.code, text, {}


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


def fp_hash(profile):
    p = DATA / profile / "fingerprint.json"
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12] if p.exists() else None


for _ in range(40):
    try:
        if call("GET", "/health")[0] == 200:
            break
    except Exception:
        time.sleep(1)

s, b, _ = call("GET", "/health")
check("health renamed", "FoxProfile" in b["message"], b["message"])

for n in ("e2e-a", "e2e-bad"):
    call("POST", f"/browser/{n}/stop")
    call("DELETE", f"/profiles/{n}")

s, b, _ = call("POST", "/profiles", {"name": "e2e-x", "os_type": "solaris"})
check("invalid os_type rejected", s == 400, f"{s} {b}")

s, b, _ = call("POST", "/profiles", {"name": "e2e-a", "os_type": "windows"})
check("create profile", s == 201, s)
s, b, _ = call("GET", "/profiles/e2e-a/fingerprint")
check("no fingerprint before first launch", b["exists"] is False, b)

t = time.time()
s, b, _ = call("POST", "/browser/e2e-a/launch")
check(
    "launch waits and reports success", s == 200 and b["success"], f"{s} {b} {time.time() - t:.1f}s"
)
h1 = fp_hash("e2e-a")
s, fp1, _ = call("GET", "/profiles/e2e-a/fingerprint")
check("fingerprint saved on first launch", fp1["exists"] and h1, fp1)

s, b, _ = call("POST", "/profiles/e2e-a/cookies", {"content": "[]"})
check("cookie import blocked while running", s == 409, f"{s} {b}")

call("POST", "/browser/e2e-a/stop")
time.sleep(2)
s, b, _ = call("POST", "/browser/e2e-a/launch")
h2 = fp_hash("e2e-a")
check("relaunch reuses same fingerprint", s == 200 and h1 == h2, f"{h1} vs {h2}")
call("POST", "/browser/e2e-a/stop")
time.sleep(2)

exp = time.time() + 86400 * 30
cookies = [
    {
        "domain": ".example.com",
        "hostOnly": False,
        "httpOnly": True,
        "name": "sid",
        "path": "/",
        "sameSite": "lax",
        "secure": True,
        "session": False,
        "expirationDate": exp,
        "value": "abc",
    },
    {
        "domain": "app.example.com",
        "hostOnly": True,
        "name": "cart",
        "path": "/",
        "session": True,
        "value": "3",
    },
]
s, b, _ = call("POST", "/profiles/e2e-a/cookies", {"content": json.dumps(cookies)})
check("import JSON cookies", s == 200 and b["success"] and b["imported"] == 2, b)

netscape = (
    ".shop.vn\tTRUE\t/\tFALSE\t0\tvisitor\txyz\n"
    f"#HttpOnly_.shop.vn\tTRUE\t/\tTRUE\t{int(exp)}\ttoken\tt0k\n"
)
s, b, _ = call("POST", "/profiles/e2e-a/cookies", {"content": netscape})
check("import Netscape cookies", s == 200 and b["imported"] == 2, b)

s, b, hdr = call("GET", "/profiles/e2e-a/cookies?format=json", raw=True)
names = sorted(c["name"] for c in json.loads(b)) if s == 200 else []
check("export JSON has all 4 cookies", names == ["cart", "sid", "token", "visitor"], f"{s} {names}")
s, b, _ = call("GET", "/profiles/e2e-a/cookies?format=netscape", raw=True)
check(
    "export Netscape", s == 200 and "#HttpOnly_.shop.vn" in b and b.startswith("# Netscape"), b[:60]
)
s, b, _ = call("GET", "/profiles/e2e-a/cookies?format=xml", raw=True)
check("unknown cookie format rejected", s == 422, s)

s, b, _ = call("DELETE", "/profiles/e2e-a/fingerprint")
check("reset fingerprint", s == 200 and fp_hash("e2e-a") is None, b)
call("POST", "/browser/e2e-a/launch")
h3 = fp_hash("e2e-a")
check("new fingerprint after reset", h3 and h3 != h1, f"{h1} -> {h3}")
call("POST", "/browser/e2e-a/stop")

# A broken fingerprint must make launch report failure instead of success.
s, b, _ = call("POST", "/profiles", {"name": "e2e-bad", "os_type": "windows"})
(DATA / "e2e-bad").mkdir(parents=True, exist_ok=True)
(DATA / "e2e-bad" / "fingerprint.json").write_text(
    json.dumps({"os": "windows", "fingerprint": {"navigator": "broken", "screen": 5}})
)
s, b, _ = call("POST", "/browser/e2e-bad/launch")
check("failed launch reports failure", s == 502 and b["success"] is False, f"{s} {b}")

for n in ("e2e-bad",):
    call("POST", f"/browser/{n}/stop")
    call("DELETE", f"/profiles/{n}")

passed = sum(ok for _, ok in results)
print(f"\n{passed}/{len(results)} checks passed")
