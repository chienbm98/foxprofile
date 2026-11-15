"""Automate the Proton VPN extension's sign-in for a profile.

The extension has no password form. Its Sign in button generates a random
`state`, stores it as `bex-f<state>`, and opens
`https://account.proton.me/authorize?...&state=...`. After the account page
authenticates the user it posts a session fork (a `payload.selector`) to the
extension's content script, which exchanges it for `UID/AccessToken/RefreshToken`
and stores the session itself. A page opened by this module with its own state
would be rejected, so the flow must start from the extension:

- Chrome: open `chrome-extension://<id>/popup.html`, click Sign in, automate the
  account tab, then confirm the extension stored a session.
- Camoufox: Marionette opens the extension's onboarding and popup pages, clicks
  Confirm choices / Sign in, and the account tab is filled with Playwright.
  `firefox_extension` also works around Firefox's missing managed-storage
  manifest, which otherwise stops the extension's background script.

Credentials are entered in the profile dialog and stored per profile by
`services.proton_account`; they are never written to `profiles.json`. A captcha, or
2FA without a TOTP secret, makes the launch fail and the profile close.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ...core import config
from ...core.logging import get_logger
from .. import proton_account
from ..proton_account import ProtonAccount
from . import firefox_extension as fx
from .extensions import PROTON_VPN

logger = get_logger("browser.proton_login")

ACCOUNT_PREFIX = "https://account.proton.me"
CHROMIUM_POPUP = f"chrome-extension://{PROTON_VPN.chromium.id}/popup.html"
MARKER = ".proton-login.json"
_CAPTCHA_MARKERS = ("captcha", "human verification", "verify you are human")
_2FA_MARKERS = ("two-factor", "2fa", "authentication code", "two factor")
_2FA_INPUTS = (
    "input#twofa",
    'input[name="twofa"]',
    'input[autocomplete="one-time-code"]',
    'input[inputmode="numeric"]',
)
_ERROR_SELECTORS = ("[role=alert]", ".error", ".notification--error")
# Records the account page's fork postMessage before the extension consumes it.
_FORK_PROBE = """
(() => {
  window.__foxprofileFork = null;
  window.addEventListener('message', (event) => {
    const data = event.data;
    if (data && data.payload && typeof data.payload.selector === 'string') {
      window.__foxprofileFork = data;
    }
  }, true);
})();
"""


def configured(profile: str) -> bool:
    """True when this profile has a Proton username and password saved."""
    return proton_account.load(profile).configured


def totp(secret: str, at: float | None = None, digits: int = 6, period: int = 30) -> str:
    """RFC 6238 code for a base32 secret (also accepts an otpauth:// URI)."""
    raw = secret.strip()
    if raw.lower().startswith("otpauth://"):
        raw = (parse_qs(urlparse(raw).query).get("secret") or [""])[0]
    clean = "".join(ch for ch in raw.upper() if ch.isalnum())
    key = base64.b32decode(clean + "=" * (-len(clean) % 8))
    counter = int((time.time() if at is None else at) // period)
    digest = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF
    return str(value % (10**digits)).zfill(digits)


def _marker(profile_dir: str | Path) -> Path:
    return Path(profile_dir) / MARKER


def logged_in_recently(profile_dir: str | Path) -> bool:
    days = config.PROTON_LOGIN_DAYS
    if days <= 0:
        return False
    try:
        data = json.loads(_marker(profile_dir).read_text(encoding="utf-8"))
        at = float(data.get("at", 0))
    except (OSError, ValueError, TypeError):
        return False
    return (time.time() - at) < days * 86_400


def _remember(profile_dir: str | Path) -> None:
    path = _marker(profile_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{time.time_ns()}.tmp")
    tmp.write_text(json.dumps({"at": int(time.time())}), encoding="utf-8")
    tmp.replace(path)


async def _visible(page: Any, selector: str) -> bool:
    with contextlib.suppress(Exception):
        return await page.locator(selector).first.is_visible()
    return False


async def _text(page: Any) -> str:
    with contextlib.suppress(Exception):
        return (await page.inner_text("body")).lower()
    return ""


async def _submit(page: Any) -> None:
    """Click the form's submit button, whichever label the page uses."""
    with contextlib.suppress(Exception):
        await page.locator('button[type="submit"]').first.click(timeout=3_000)
        return
    for label in ("continue", "sign in", "next", "verify", "unlock"):
        with contextlib.suppress(Exception):
            await page.get_by_role("button", name=label, exact=False).first.click(timeout=2_000)
            return


async def _error(page: Any) -> str:
    for selector in _ERROR_SELECTORS:
        with contextlib.suppress(Exception):
            locator = page.locator(selector).first
            if await locator.is_visible():
                return " ".join((await locator.inner_text()).split())[:200]
    return ""


async def _fork_received(page: Any) -> bool:
    with contextlib.suppress(Exception):
        return bool(await page.evaluate("() => Boolean(window.__foxprofileFork)"))
    return False


async def _sign_in(page: Any, account: ProtonAccount) -> tuple[bool, str]:
    """Fill the account page. Success means the page posted its session fork."""
    with contextlib.suppress(Exception):
        await page.add_init_script(_FORK_PROBE)
    with contextlib.suppress(Exception):
        await page.evaluate(_FORK_PROBE)
    deadline = time.monotonic() + 120
    started = time.monotonic()
    fallback_done = False
    switch_sent = False
    username_sent = password_sent = twofa_sent = False
    while time.monotonic() < deadline:
        await page.wait_for_timeout(500)
        if await _fork_received(page):
            return True, "signed in"
        text = await _text(page)
        # The authorize flow's success page. Do not trust success wording in the
        # sign-in page's hidden templates: it made the form look already done.
        if "/auth-ext" in page.url:
            return True, "signed in"
        if any(marker in text for marker in _CAPTCHA_MARKERS):
            return False, "human verification is required; sign in once by hand"
        if not switch_sent and (
            "/switch" in page.url
            or "choose account" in text.lower()
            or "chọn tài khoản" in text.lower()
        ):
            # Proton keeps the account session in a cookie. The extension's
            # authorize page then shows "Choose account" instead of a form;
            # click the row for this profile's username (or the only row).
            switch_sent = True
            with contextlib.suppress(Exception):
                rows = page.locator("a.expand-click-area")
                count = await rows.count()
                chosen = None
                for index in range(count):
                    row = rows.nth(index)
                    label = await row.inner_text()
                    if account.username.lower() in label.lower():
                        chosen = row
                        break
                if chosen is None and count:
                    chosen = rows.first
                if chosen is not None:
                    await chosen.click(timeout=8_000)
                    continue
        if (
            not fallback_done
            and time.monotonic() - started > 12
            and not username_sent
            and not password_sent
            and not await _visible(page, "input#username")
        ):
            # The authorize page can stay on a blank/consent screen; the
            # account sign-in page always renders the form.
            fallback_done = True
            with contextlib.suppress(Exception):
                await page.goto(
                    "https://account.proton.me/vpn",
                    wait_until="domcontentloaded",
                    timeout=30_000,
                )
            continue
        if not username_sent and await _visible(page, "input#username"):
            try:
                await page.fill("input#username", account.username, timeout=5_000)
                await _submit(page)
                username_sent = True
            except Exception as e:
                return False, f"could not fill the username: {type(e).__name__}"
            continue
        if not password_sent and await _visible(page, "input[type=password]"):
            try:
                await page.fill("input[type=password]", account.password, timeout=5_000)
                await _submit(page)
                password_sent = True
            except Exception as e:
                return False, f"could not fill the password: {type(e).__name__}"
            continue
        if not twofa_sent and any(marker in text for marker in _2FA_MARKERS):
            if not account.totp:
                return (
                    False,
                    "two-factor is required; save the TOTP secret in the app or sign in by hand",
                )
            try:
                code = totp(account.totp)
                for selector in _2FA_INPUTS:
                    if await _visible(page, selector):
                        await page.fill(selector, code, timeout=5_000)
                        break
                else:
                    return False, "could not find the two-factor input"
                await _submit(page)
                twofa_sent = True
            except Exception as e:
                return False, f"could not submit the two-factor code: {type(e).__name__}"
            continue
        error = await _error(page)
        if error:
            return False, f"Proton rejected the sign-in: {error}"
    title = ""
    with contextlib.suppress(Exception):
        title = await page.title()
    snippet = " | ".join((await _text(page)).split())[:160]
    return False, f"timed out waiting for the sign-in form ({page.url} · {title} · {snippet})"


async def _chromium_session(context: Any) -> tuple[Any, dict]:
    """Open the extension popup and read its stored session (Chrome only)."""
    page = await context.new_page()
    await page.goto(CHROMIUM_POPUP, wait_until="domcontentloaded", timeout=20_000)
    session = await page.evaluate("async () => await chrome.storage.local.get('bex-session')")
    return page, session.get("bex-session") or {}


async def _chromium_popup_logged(page: Any) -> bool:
    """True when the Chrome popup shows its signed-in view."""
    try:
        await page.wait_for_selector("#logged-view", state="visible", timeout=5_000)
        return True
    except Exception:  # noqa: BLE001
        return False


async def _connect_country(context: Any, country: str, log: Any) -> bool:
    """Pick the country in the extension popup and wait until it connects."""
    code = country.strip().upper()
    page = None
    try:
        page = await context.new_page()
        await page.goto(CHROMIUM_POPUP, wait_until="domcontentloaded", timeout=20_000)
        current = await page.evaluate(
            """async () => {
              const data = await chrome.storage.session.get('bex-connectedServer');
              return (data && data['bex-connectedServer'] && data['bex-connectedServer'].value) || null;
            }"""
        )
        if current and current.get("name"):
            exit_country = str(current.get("exitCountry") or "").upper()
            if not code or exit_country == code:
                log(f"Proton login: connected to {current['name']} ({exit_country or 'fastest'})")
                return True
            await page.locator(".disconnection-button").click(timeout=10_000)
            for _ in range(30):
                value = await page.evaluate(
                    """async () => {
                      const data = await chrome.storage.session.get('bex-connectedServer');
                      return (data && data['bex-connectedServer'] && data['bex-connectedServer'].value) || null;
                    }"""
                )
                if not value or not value.get("name"):
                    break
                await asyncio.sleep(0.5)

        if code:
            selector = f'.country-name[data-country-code="{code}"]'
            await page.wait_for_selector(selector, state="attached", timeout=30_000)
            button = page.locator(f"button.connect-option:has({selector})").first
            await button.scroll_into_view_if_needed(timeout=10_000)
            await button.click(timeout=10_000)
        else:
            await page.locator(".quick-connect-button").click(timeout=10_000)

        for _ in range(60):
            value = await page.evaluate(
                """async () => {
                  const data = await chrome.storage.session.get('bex-connectedServer');
                  return (data && data['bex-connectedServer'] && data['bex-connectedServer'].value) || null;
                }"""
            )
            if value and value.get("name"):
                exit_country = str(value.get("exitCountry") or "").upper()
                if not code or exit_country == code:
                    log(f"Proton login: connected to {value['name']} ({exit_country or code})")
                    return True
            await asyncio.sleep(0.5)
        target = code or "the fastest server"
        log(f"Proton login: signed in, but {target} did not connect (free-tier restriction?)")
        return False
    except Exception as e:
        log(f"Proton login: could not select {code or 'the fastest server'}: {type(e).__name__}")
        return False
    finally:
        if page is not None and not page.is_closed():
            with contextlib.suppress(Exception):
                await page.close()


async def _probe_connected(page: Any, country: str = "") -> bool:
    with contextlib.suppress(Exception):
        value = await page.evaluate(
            """async () => {
              const data = await chrome.storage.session.get('bex-connectedServer');
              const entry = data && data['bex-connectedServer'];
              return (entry && entry.value) || null;
            }"""
        )
        if not value or not value.get("name"):
            return False
        if not country:
            return True
        return str(value.get("exitCountry") or "").upper() == country.strip().upper()
    return False


async def ensure_connected(
    context: Any,
    country: str,
    log: Any,
    timeout: float = 120,
) -> bool:
    """Wait until the extension reports a connected server, connecting first if asked.

    Used before restoring tabs: the profile must not load browsing tabs on the
    real IP while the VPN is still signing in.
    """
    code = country.strip().upper()
    probe, _ = await _chromium_session(context)
    try:
        if await _probe_connected(probe, code):
            return True
        await _connect_country(context, country, log)
        deadline = time.monotonic() + timeout
        last_log = time.monotonic()
        while time.monotonic() < deadline:
            if probe.is_closed():
                probe, _ = await _chromium_session(context)
            if await _probe_connected(probe, code):
                return True
            if time.monotonic() - last_log > 15:
                last_log = time.monotonic()
                log("Proton login: waiting for the VPN to connect; tabs stay closed")
            await asyncio.sleep(1)
        log("Proton login: the VPN did not connect in time; tabs stay closed")
        return False
    finally:
        if not probe.is_closed():
            with contextlib.suppress(Exception):
                await probe.close()


async def _chromium_login(
    context: Any,
    profile_dir: str | Path,
    account: ProtonAccount,
    *,
    keep_open: bool,
    log: Any,
    country: str = "",
) -> bool:
    probe, session = await _chromium_session(context)
    if session.get("uid") and await _chromium_popup_logged(probe):
        log("Proton login: the extension is already signed in")
        _remember(profile_dir)
        await probe.close()
        await _connect_country(context, country, log)
        return True
    if session.get("uid"):
        log("Proton login: the stored session has expired; signing in again")

    account_page = None
    before = {id(page) for page in context.pages}
    await _clear_account_cookies(context)
    with contextlib.suppress(Exception):
        # A trusted click lets the extension request its optional proxy
        # permission. The popup closes itself right after it.
        await probe.locator(".sign-in-button").click(timeout=5_000)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        account_page = next(
            (
                page
                for page in context.pages
                if id(page) not in before and page.url.startswith(ACCOUNT_PREFIX)
            ),
            None,
        )
        if account_page is not None:
            break
        # A fresh tab can stay on about:blank for a moment.
        fresh = [page for page in context.pages if id(page) not in before]
        if any(page.url == "about:blank" for page in fresh):
            await asyncio.sleep(0.5)
            continue
        await asyncio.sleep(0.5)

    try:
        if account_page is None:
            log("Proton login: the extension did not open its sign-in page")
            return False
        ok, message = await _sign_in(account_page, account)
        if not ok:
            log(f"Proton login: {message}")
            return False

        # The extension consumes the fork asynchronously; wait for its session.
        for _ in range(20):
            if probe.is_closed():
                probe, session = await _chromium_session(context)
            else:
                session = (
                    await probe.evaluate(
                        "async () => await chrome.storage.local.get('bex-session')"
                    )
                ).get("bex-session") or {}
            if session.get("uid"):
                _remember(profile_dir)
                log("Proton login: signed in; the VPN extension has the session")
                if account_page is not None and not account_page.is_closed():
                    with contextlib.suppress(Exception):
                        await account_page.close()
                await _connect_country(context, country, log)
                return True
            await asyncio.sleep(0.5)
        log("Proton login: signed in, but the extension did not store the session")
        return False
    finally:
        if account_page is not None and not keep_open:
            with contextlib.suppress(Exception):
                await account_page.close()
        if not probe.is_closed():
            with contextlib.suppress(Exception):
                await probe.close()


async def _clear_account_cookies(context: Any) -> None:
    """Log the Proton account out of this profile so the sign-in form appears.

    The extension's authorize page otherwise shows a "Choose account" screen,
    and that path drops the state the extension needs to accept its session
    fork. Only the account site's cookies and local storage are cleared; other
    Proton services and the rest of the profile stay intact.
    """
    for domain in ("account.proton.me", "proton.me", ".proton.me"):
        with contextlib.suppress(Exception):
            await context.clear_cookies(domain=domain)
    page = None
    try:
        page = await context.new_page()
        await page.goto(
            "https://account.proton.me/login",
            wait_until="domcontentloaded",
            timeout=20_000,
        )
        await page.evaluate(
            """async () => {
              localStorage.clear();
              sessionStorage.clear();
              for (const database of await indexedDB.databases()) {
                if (database.name) indexedDB.deleteDatabase(database.name);
              }
            }"""
        )
    except Exception:  # noqa: BLE001 - the next step reports the real failure
        pass
    finally:
        if page is not None and not page.is_closed():
            with contextlib.suppress(Exception):
                await page.close()


async def _wait_for_account_page(context: Any, timeout: float = 25.0) -> Any:
    """Return the account tab the extension opens, or None."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for page in context.pages:
            with contextlib.suppress(Exception):
                if page.url.startswith(ACCOUNT_PREFIX):
                    return page
        await asyncio.sleep(0.4)
    return None


def _camoufox_prepare(client: Any, log: Any) -> None:
    """Make Firefox's managed-storage lookup work and grant the proxy API."""
    fx.patch_managed_storage(client)
    if not fx.grant_proxy(client):
        log("Proton login: could not grant the extension's proxy permission")
    fx.reload_extension(client)


def _camoufox_onboard(client: Any, log: Any) -> None:
    """Complete the first-run page before opening the popup.

    On a fresh profile the extension closes a popup that is opened before its
    onboarding page has been acknowledged. Clicking Confirm choices (when the
    page offers it) makes the popup stay open.
    """
    if not fx.open_page(client, fx.ONBOARDING) or not fx.select_page(client, fx.ONBOARDING):
        log("Proton login: could not open the extension onboarding page")
        return
    fx.click(client, ".consent-button")
    time.sleep(1)
    fx.close_page(client, fx.ONBOARDING)


def _camoufox_popup(client: Any, log: Any) -> dict:
    """Open the extension popup and wait until it has selected a view."""
    for attempt in range(3):
        if attempt:
            fx.close_page(client, fx.POPUP)
            time.sleep(1)
        if not fx.open_page(client, fx.POPUP):
            log("Proton login: could not open the extension popup")
            return {}
        if not fx.select_page(client, fx.POPUP):
            log("Proton login: the extension popup did not load")
            continue
        state = fx.wait_popup(client, timeout=25)
        if state:
            # The extension writes the connection state just after the popup appears.
            time.sleep(2)
            return state
    return {}


async def _camoufox_wait_logged(client: Any, log: Any, timeout: float = 30.0) -> dict:
    """Reopen the popup until it shows the signed-in view."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = await asyncio.to_thread(_camoufox_popup, client, log)
        if state.get("logged") == "block":
            return state
        if state.get("signin") == "block":
            fx.close_page(client, fx.POPUP)
            await asyncio.sleep(1)
            continue
        await asyncio.sleep(1)
    return {}


async def _camoufox_login(
    context: Any,
    client: Any,
    profile_dir: str | Path,
    account: ProtonAccount,
    log: Any,
) -> bool:
    """Sign in through the extension's own onboarding page."""
    log("Proton login: signing in through the extension")
    await _clear_account_cookies(context)
    if not fx.open_page(client, fx.ONBOARDING) or not fx.select_page(client, fx.ONBOARDING):
        log("Proton login: could not open the extension onboarding page")
        return False
    fx.click(client, ".consent-button")
    await asyncio.sleep(1)
    if not fx.click(client, ".login-button"):
        log("Proton login: the extension has no sign-in button")
        return False

    account_page = await _wait_for_account_page(context)
    if account_page is None:
        log("Proton login: the extension did not open the account page")
        return False
    try:
        ok, message = await _sign_in(account_page, account)
        if not ok:
            log(f"Proton login: {message}")
            return False
        _remember(profile_dir)
        log("Proton login: signed in; waiting for the extension to store the session")
        return True
    finally:
        if not account_page.is_closed():
            with contextlib.suppress(Exception):
                await account_page.close()
        fx.close_page(client, fx.ONBOARDING)


def _status_label(status: str) -> str:
    lines = [line.strip() for line in status.splitlines() if line.strip()]
    return lines[1] if len(lines) > 1 else ""


def _camoufox_matches(value: dict, state: dict, code: str, label: str) -> bool:
    """True when the popup says it is protected by the requested country."""
    if value.get("name"):
        if not code:
            return True
        return str(value.get("exitCountry") or "").upper() == code
    if state.get("connected"):
        return not code or bool(label and label in str(state.get("status") or ""))
    return False


async def _camoufox_wait_state(client: Any, timeout: float = 10.0) -> tuple[dict, dict]:
    """Let the popup settle: wait for auto-connect or a disconnected view."""
    deadline = time.monotonic() + timeout
    value: dict = {}
    state: dict = {}
    while time.monotonic() < deadline:
        value = fx.connected_value(client)
        state = fx.page_state(client)
        if value.get("name") or state.get("connected") or state.get("disconnected"):
            return value, state
        await asyncio.sleep(0.5)
    return value, state


async def _camoufox_disconnect(client: Any, log: Any) -> bool:
    """Disconnect before switching to another country (clicking the same row toggles)."""
    if not fx.click(client, ".disconnection-button"):
        return False
    log("Proton login: disconnecting from the current server")
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        state = fx.page_state(client)
        if state.get("disconnected") and not fx.connected_value(client).get("name"):
            return True
        await asyncio.sleep(0.5)
    return False


async def _camoufox_connect(client: Any, country: str, log: Any, timeout: float = 120) -> bool:
    """Pick a country in the popup and wait for the extension to connect."""
    state = _camoufox_popup(client, log)
    if not state:
        return False
    if state.get("signin") == "block":
        fx.close_page(client, fx.POPUP)
        return False
    if state.get("logged") != "block":
        log("Proton login: the extension popup did not become ready")
        fx.close_page(client, fx.POPUP)
        return False

    code = country.strip().upper()
    label = fx.country_name(client, code) if code else ""
    current, state = await _camoufox_wait_state(client)
    if _camoufox_matches(current, state, code, label):
        exit_country = str(current.get("exitCountry") or code or "fastest").upper()
        log(
            f"Proton login: connected to "
            f"{current.get('name') or _status_label(state.get('status', ''))} ({exit_country})"
        )
        fx.close_page(client, fx.POPUP)
        return True

    # A restored connection can still be starting; give it time to settle
    # before deciding whether to switch.
    if not state.get("connected") and not state.get("disconnected"):
        current, state = await _camoufox_wait_state(client, timeout=30)
        if _camoufox_matches(current, state, code, label):
            log(f"Proton login: connected to {current.get('name') or label} ({code or 'fastest'})")
            fx.close_page(client, fx.POPUP)
            return True
    elif state.get("disconnected"):
        await asyncio.sleep(3)
        current, state = await _camoufox_wait_state(client, timeout=5)
        if _camoufox_matches(current, state, code, label):
            log(f"Proton login: connected to {current.get('name') or label} ({code or 'fastest'})")
            fx.close_page(client, fx.POPUP)
            return True

    if (current.get("name") or state.get("connected")) and not await _camoufox_disconnect(
        client, log
    ):
        log("Proton login: could not disconnect from the previous server")
        fx.close_page(client, fx.POPUP)
        return False

    if code:
        if not fx.click_country(client, code):
            log(f"Proton login: {code} is not available in the extension")
            fx.close_page(client, fx.POPUP)
            return False
        log(f"Proton login: connecting to {code}...")
    else:
        if not fx.click(client, ".quick-connect-button"):
            log("Proton login: the extension has no quick-connect button")
            fx.close_page(client, fx.POPUP)
            return False
        log("Proton login: connecting to the fastest server...")

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = fx.connected_value(client)
        state = fx.page_state(client)
        if _camoufox_matches(value, state, code, label):
            exit_country = str(value.get("exitCountry") or code or "fastest").upper()
            log(f"Proton login: connected to {value.get('name') or label} ({exit_country})")
            fx.close_page(client, fx.POPUP)
            return True
        await asyncio.sleep(0.5)
    log("Proton login: the VPN did not connect in time")
    fx.close_page(client, fx.POPUP)
    return False


async def _camoufox_auto_login(
    context: Any,
    profile_dir: str | Path,
    account: ProtonAccount,
    *,
    marionette_port: int,
    log: Any,
    country: str,
) -> bool:
    client = None
    try:
        client = await asyncio.to_thread(fx.connect, marionette_port)
        await asyncio.to_thread(_camoufox_prepare, client, log)
        await asyncio.to_thread(_camoufox_onboard, client, log)
        state = await asyncio.to_thread(_camoufox_popup, client, log)
        if not state:
            return False
        if state.get("signin") == "block":
            fx.close_page(client, fx.POPUP)
            if not await _camoufox_login(context, client, profile_dir, account, log):
                return False
            state = await _camoufox_wait_logged(client, log)
            if not state:
                log("Proton login: the extension did not store the session")
                return False
        elif state.get("logged") != "block":
            log("Proton login: the extension popup did not become ready")
            return False
        return await _camoufox_connect(client, country, log)
    except Exception as e:
        log(f"Proton login failed: {type(e).__name__}: {' '.join(str(e).split())[:200]}")
        return False
    finally:
        if client is not None:
            await asyncio.to_thread(fx.close, client)


async def auto_login(
    context: Any,
    profile_dir: str | Path,
    engine: str,
    profile: str,
    *,
    keep_open: bool = False,
    log: Any = print,
    country: str = "",
    marionette_port: int = 0,
) -> bool:
    """Sign in and connect the Proton VPN extension for a profile.

    Chrome uses Playwright. Camoufox opens the extension's pages through
    Marionette. The function never raises to the caller; a false result tells
    the runner to close the profile and report LAUNCH_FAILED.
    """
    account = proton_account.load(profile)
    if not account.configured:
        return False
    try:
        if engine == "chrome":
            return await _chromium_login(
                context,
                profile_dir,
                account,
                keep_open=keep_open,
                log=log,
                country=country,
            )
        if engine != "camoufox":
            return False
        if not marionette_port:
            log("Proton login: Camoufox was started without a Marionette port")
            return False
        return await _camoufox_auto_login(
            context,
            profile_dir,
            account,
            marionette_port=marionette_port,
            log=log,
            country=country,
        )
    except Exception as e:
        log(f"Proton login failed: {type(e).__name__}: {' '.join(str(e).split())[:200]}")
        return False
