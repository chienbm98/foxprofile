import base64
import os
import pathlib
import sys
import time

os.environ["FOXPROFILE_HEADLESS"] = "true"
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from src.models.profile import Profile
from src.services.browser.launcher import BrowserControlError, BrowserLauncher

bl = BrowserLauncher()
p = Profile(name="ctl-test", os_type="windows")
t = time.time()
bl.start_thread(p, lambda m: None)
print("launch:", bl.wait_for_launch("ctl-test", 90), f"{time.time() - t:.1f}s")

r = bl.control("ctl-test", "navigate", {"url": "example.com"})
print("navigate:", r)
snap = bl.control("ctl-test", "snapshot")
print("snapshot:", snap["snapshot"][:200].replace("\n", " | "))
print("click:", bl.control("ctl-test", "click", {"selector": "role=link"}))
shot = bl.control("ctl-test", "screenshot")
png = base64.b64decode(shot["png_base64"])
print("screenshot bytes:", len(png), png[:4])
print("evaluate:", bl.control("ctl-test", "evaluate", {"script": "navigator.webdriver"}))
print("tab_new:", bl.control("ctl-test", "tab_new", {"url": "https://example.org"})["tabs"])
print("tab_close 0:", [t["url"] for t in bl.control("ctl-test", "tab_close", {"index": 0})["tabs"]])
print("still running after closing a tab:", bl.is_running("ctl-test"))
for bad in [
    ("navigate", {"url": "file:///C:/Windows/win.ini"}),
    ("explode", {}),
    ("click", {"selector": "#nope", "timeout": 1500}),
    ("click", {"wrong": 1}),
]:
    try:
        bl.control("ctl-test", *bad)
        print("UNEXPECTED success", bad)
    except BrowserControlError as e:
        print(f"rejected {bad[0]}: [{e.status}] {str(e)[:90]}")
bl.stop_profile("ctl-test")
try:
    bl.control("ctl-test", "tabs")
except BrowserControlError as e:
    print("after stop:", e.status, e)
