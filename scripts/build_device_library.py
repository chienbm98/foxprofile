"""Build src/assets/devices/devices.json (real desktop Firefox device records).

Two steps, because browserforge must never enter the project venv:

1. Sample apify fingerprint-suite data (needs a throwaway venv with
   `pip install browserforge apify_fingerprint_datapoints`; it is Apache-2.0):
       <throwaway>/bin/python scripts/build_device_library.py sample RAW.json --seed 1 --n 20000
2. Filter and write the library (project venv, camoufox installed and fetched):
       .venv/bin/python scripts/build_device_library.py build RAW.json

Output is deterministic for a given RAW.json and camoufox version. Sources and
licenses: src/assets/devices/NOTICE.md.
"""

import argparse
import collections
import hashlib
import json
import random
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "src" / "assets" / "devices" / "devices.json"
OSES = {"windows": "win", "macos": "mac", "linux": "lin"}
CAP = 400  # records per OS
SCREEN = ("width", "height", "colorDepth", "availWidth", "availHeight", "devicePixelRatio")
NAV = ("userAgent", "platform", "hardwareConcurrency", "maxTouchPoints")
FIELDS = {
    "navigator": (*NAV, "oscpu"),
    "screen": SCREEN,
    "webgl": ("unmaskedVendor", "unmaskedRenderer"),
}
REQUIRED = {**FIELDS, "navigator": NAV}


def sample(path, seed, n):
    from browserforge.fingerprints import FingerprintGenerator

    random.seed(seed)
    raw = {}
    for os_name in OSES:
        gen = FingerprintGenerator(browser="firefox", os=os_name, device="desktop")
        recs = {}
        for _ in range(n):
            f = gen.generate()
            nav, scr, vc = f.navigator, f.screen, f.videoCard
            rec = {
                "navigator": {
                    "userAgent": nav.userAgent,
                    "platform": nav.platform,
                    "hardwareConcurrency": nav.hardwareConcurrency,
                    "maxTouchPoints": nav.maxTouchPoints,
                    "oscpu": nav.oscpu,
                },
                "screen": {
                    k: getattr(scr, k)
                    for k in (
                        "width",
                        "height",
                        "colorDepth",
                        "availWidth",
                        "availHeight",
                        "devicePixelRatio",
                    )
                },
                "webgl": {"unmaskedVendor": vc.vendor, "unmaskedRenderer": vc.renderer},
            }
            recs[json.dumps(rec, sort_keys=True)] = rec
        raw[os_name] = list(recs.values())
    Path(path).write_text(json.dumps(raw))


def dedupe_key(os_name, rec):
    nav, scr, gl = rec["navigator"], rec["screen"], rec["webgl"]
    ua_os = re.search(r"\(([^)]*)\)", nav["userAgent"]).group(1)
    return (os_name, ua_os, nav["platform"], nav["hardwareConcurrency"], scr["width"], scr["height"],
            scr["devicePixelRatio"], gl["unmaskedVendor"], gl["unmaskedRenderer"])  # fmt: skip


def check(os_name, rec, gpus, stats):
    """Return the reason to drop `rec`, or None. Counts rule hits in stats."""
    from camoufox import coherence
    from camoufox.fingerprints import gpu_screen_is_plausible, is_software_renderer
    from camoufox.utils import launch_options

    key = OSES[os_name]
    nav, scr, gl = rec["navigator"], rec["screen"], rec["webgl"]
    gpu = (gl["unmaskedVendor"], gl["unmaskedRenderer"])
    if gpu[1] == "Mozilla" or is_software_renderer(gpu[1]):
        return "software-renderer"
    if gpu not in gpus:
        return "gpu-not-in-firefox_gpus"
    if not coherence.gpu_fits_os(gpu[1], key):
        return "gpu-not-fit-os"
    if scr["width"] < 1280 or scr["height"] < 720:
        return "screen-too-small"
    if key == "mac" and scr["height"] < 800:  # no Mac ships a smaller logical screen
        return "mac-screen-floor"
    if scr["devicePixelRatio"] not in coherence.PLAUSIBLE_DPR[key]:
        return "dpr"  # a browser zoom folded into the ratio, not a display mode
    if key == "mac":
        # The largest Mac panel is the 6016x3384 Pro Display XDR.
        if (
            scr["width"] * scr["devicePixelRatio"] > 6016
            or scr["height"] * scr["devicePixelRatio"] > 3384
        ):
            return "mac-physical-screen"
        # Intel-era Macs with these GPU buckets topped out at 8 threads (bar a rare Mac Pro).
        if not gpu[1].startswith("Apple") and nav["hardwareConcurrency"] > 8:
            return "intel-mac-cores"
    try:
        opts = launch_options(
            os=os_name, headless=True, fingerprint_preset=rec, i_know_what_im_doing=True
        )
    except Exception as e:  # noqa: BLE001
        return f"launch-error:{type(e).__name__}"
    env = opts["env"]
    names = sorted(
        (k for k in env if k.startswith("CAMOU_CONFIG_")), key=lambda k: int(k.rsplit("_", 1)[1])
    )
    cfg = json.loads("".join(env[k] for k in names))
    got = (
        cfg.get("webGl:vendor"),
        cfg.get("webGl:renderer"),
        cfg.get("screen.width"),
        cfg.get("screen.height"),
    )
    if got != (*gpu, scr["width"], scr["height"]):
        return "launch-repaired"  # camoufox itself rewrote gpu/screen: not a coherent device
    if not gpu_screen_is_plausible(gpu[1], scr["width"], scr["height"]):
        return "gpu-screen"
    for v in coherence.validate(cfg, key):
        return f"coherence:{v.rule}"
    return None


def build(raw_path):
    import camoufox.utils
    from camoufox import __file__ as cf_file
    from camoufox.webgl import firefox_gpus

    # launch_options replaces cores with the host's count before judging; judge the record's own.
    camoufox.utils.fix_hardware_concurrency = lambda *a, **k: None
    cdir = Path(cf_file).parent
    sources = []
    for name, fname in (("camoufox-presets-v150", "fingerprint-presets-v150.json"),
                        ("camoufox-presets", "fingerprint-presets.json")):  # fmt: skip
        presets = json.loads((cdir / fname).read_text())["presets"]
        sources.append((name, presets))
    sources.append(("apify-fingerprint-suite", json.loads(Path(raw_path).read_text())))

    lib = {os_name: [] for os_name in OSES}
    seen = set()
    stats = collections.defaultdict(collections.Counter)  # (source, os) -> reason counts
    for os_name in OSES:
        gpus = firefox_gpus(OSES[os_name])
        for src, presets in sources:
            for rec in presets.get(os_name, []):
                stats[src, os_name]["input"] += 1
                try:  # keep only the preset fields (drops speechVoices etc.)
                    rec = {
                        part: {k: rec[part][k] for k in keys if k in rec[part]}
                        for part, keys in FIELDS.items()
                    }
                    if any(k not in rec[part] for part, keys in REQUIRED.items() for k in keys):
                        raise KeyError
                except KeyError:
                    stats[src, os_name]["missing-field"] += 1
                    continue
                # Camoufox cannot fake touch events, so a touch-point count contradicts them.
                rec["navigator"]["maxTouchPoints"] = 0
                key = dedupe_key(os_name, rec)
                if key in seen:
                    stats[src, os_name]["duplicate"] += 1
                    continue
                why = check(os_name, rec, gpus, stats)
                if why:
                    stats[src, os_name][why] += 1
                    continue
                seen.add(key)
                digest = hashlib.sha1(repr(key).encode()).hexdigest()[:10]
                lib[os_name].append({"id": f"{os_name[:3]}-{digest}", "source": src, **rec})
    # Cap per OS, keeping every bundled record first and a seeded diverse sample of the rest.
    rng = random.Random(0)
    for os_name, recs in lib.items():
        if len(recs) > CAP:
            bundled = [r for r in recs if r["source"] != "apify-fingerprint-suite"]
            rest = [r for r in recs if r["source"] == "apify-fingerprint-suite"]
            rng.shuffle(rest)
            keep = bundled + rest[: max(0, CAP - len(bundled))]
            stats["apify-fingerprint-suite", os_name]["capped-out"] += len(recs) - len(keep)
            recs[:] = keep
        recs.sort(key=lambda r: r["id"])
    OUT.write_text(
        json.dumps({"version": 1, "presets": lib}, separators=(",", ":"), sort_keys=True) + "\n"
    )
    for (src, os_name), c in sorted(stats.items()):
        kept = sum(1 for r in lib[os_name] if r["source"] == src)
        print(f"{src:26s} {os_name:8s} kept={kept} {dict(c)}")
    print({o: len(r) for o, r in lib.items()}, OUT.stat().st_size, "bytes")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("mode", choices=["sample", "build"])
    ap.add_argument("raw")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--n", type=int, default=20000)
    a = ap.parse_args()
    sample(a.raw, a.seed, a.n) if a.mode == "sample" else build(a.raw)
    sys.exit(0)
