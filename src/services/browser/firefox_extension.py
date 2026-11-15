"""Marionette helpers for a Camoufox extension page.

Playwright can drive normal pages but cannot open a ``moz-extension://`` page,
so the Proton VPN extension's own popup and onboarding pages are opened and
clicked through Marionette. The helpers here are deliberately small: they
speak only to the extension's pages and storage, never to arbitrary sites.

The Proton extension calls ``storage.managed.get()`` while it starts. Firefox
raises ``Managed storage manifest not found`` when no enterprise manifest is
installed (Chrome returns an empty object), and that unhandled rejection stops
the extension's background script. :func:`patch_managed_storage` makes that one
lookup resolve to an empty object for this browser process only; the extension
is then reloaded so its background starts cleanly.
"""

from __future__ import annotations

import contextlib
import json
import time
from typing import Any

from .extensions import PROTON_VPN

EXTENSION_ID = PROTON_VPN.firefox.id
ONBOARDING = "onboarding.html"
POPUP = "popup.html"


def connect(port: int, timeout: float = 30.0) -> Any:
    """Return a started Marionette client for ``port``.

    Camoufox takes a few seconds to open the port. ``marionette-driver`` is a
    synchronous client; every call here is short except this initial wait.
    """
    from marionette_driver.marionette import Marionette

    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            client = Marionette(host="127.0.0.1", port=port, socket_timeout=10)
            client.start_session()
            return client
        except Exception as e:  # noqa: BLE001 - the browser is still starting
            last = e
            time.sleep(0.5)
    raise RuntimeError(f"Marionette did not start on port {port}: {last}")


def close(client: Any) -> None:
    """End the Marionette session without closing the browser."""
    with contextlib.suppress(Exception):
        client.delete_session()


def _chrome(client: Any) -> None:
    client.set_context("chrome")


def _content(client: Any) -> None:
    client.set_context("content")


def _script(client: Any, script: str, args: list[Any] | None = None) -> Any:
    _chrome(client)
    return client.execute_script(script, script_args=args or [])


def _async_script(client: Any, script: str, args: list[Any] | None = None) -> Any:
    _chrome(client)
    return client.execute_async_script(script, script_args=args or [])


def patch_managed_storage(client: Any) -> None:
    """Make Firefox's missing managed-storage manifest behave like Chrome's."""
    _script(
        client,
        """
        const { NativeManifests } = ChromeUtils.importESModule(
          "resource://gre/modules/NativeManifests.sys.mjs"
        );
        if (!NativeManifests.__foxprofilePatched) {
          const original = NativeManifests.lookupManifest.bind(NativeManifests);
          NativeManifests.lookupManifest = (type, name, context) =>
            type === "storage"
              ? Promise.resolve({
                  path: "foxprofile:",
                  manifest: { name, type: "storage", data: {} },
                })
              : original(type, name, context);
          NativeManifests.__foxprofilePatched = true;
        }
        """,
    )


def grant_proxy(client: Any) -> bool:
    """Grant the optional ``proxy`` permission without a user gesture."""
    result = _async_script(
        client,
        """
        const cb = arguments[arguments.length - 1];
        const done = arguments[0];
        const { ExtensionPermissions } = ChromeUtils.importESModule(
          "resource://gre/modules/ExtensionPermissions.sys.mjs"
        );
        ExtensionPermissions.add(done, { permissions: ["proxy"], origins: [] })
          .then(() => cb(true))
          .catch(() => cb(false));
        """,
        [EXTENSION_ID],
    )
    return bool(result)


def wait_for_extension(client: Any, timeout: float = 20.0) -> bool:
    """Wait until the add-on is loaded and its background context is up."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = _async_script(
            client,
            """
            const cb = arguments[arguments.length - 1];
            const done = arguments[0];
            (async () => {
              const { AddonManager } = ChromeUtils.importESModule(
                "resource://gre/modules/AddonManager.sys.mjs"
              );
              const addon = await AddonManager.getAddonByID(done);
              const policy = WebExtensionPolicy.getByID(done);
              const extension = policy && policy.extension;
              return {
                addon: !!addon,
                policy: !!policy,
                extension: !!extension,
                background: extension ? extension._backgroundState : null,
              };
            })().then((value) => cb(value)).catch((error) => cb({ error: String(error) }));
            """,
            [EXTENSION_ID],
        )
        if isinstance(state, dict) and state.get("extension"):
            return True
        time.sleep(0.5)
    return False


def reload_extension(client: Any, timeout: float = 30.0) -> None:
    """Restart the add-on so it picks up the managed-storage patch and proxy."""
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            result = _async_script(
                client,
                """
                const cb = arguments[arguments.length - 1];
                const done = arguments[0];
                const { AddonManager } = ChromeUtils.importESModule(
                  "resource://gre/modules/AddonManager.sys.mjs"
                );
                (async () => {
                  const addon = await AddonManager.getAddonByID(done);
                  if (!addon) throw new Error("extension is not loaded");
                  await addon.disable();
                  await addon.enable();
                  return true;
                })().then((value) => cb(value)).catch((error) => cb(String(error)));
                """,
                [EXTENSION_ID],
            )
            if result is True and wait_for_extension(client, timeout=15):
                # The background is lazy in Firefox; wake it once so the
                # popup's first runtime message does not time out.
                _async_script(
                    client,
                    """
                    const cb = arguments[arguments.length - 1];
                    const policy = WebExtensionPolicy.getByID(arguments[0]);
                    if (!policy || !policy.extension) return cb(false);
                    policy.extension.wakeupBackground()
                      .then(() => cb(true))
                      .catch(() => cb(false));
                    """,
                    [EXTENSION_ID],
                )
                time.sleep(1)
                return
            last = RuntimeError(str(result))
        except Exception as e:  # noqa: BLE001 - retry while the add-on loads
            last = e
        time.sleep(1)
    raise RuntimeError(f"could not reload {EXTENSION_ID}: {last}")


def open_page(client: Any, name: str) -> bool:
    """Open one of the extension's pages as a tab."""
    result = _script(
        client,
        """
        const done = arguments[0];
        const policy = WebExtensionPolicy.getByID(arguments[1]);
        if (!policy) return false;
        const url = policy.getURL(done);
        const tab = gBrowser.addTab(url, {
          triggeringPrincipal: Services.scriptSecurityManager.getSystemPrincipal(),
        });
        gBrowser.selectedTab = tab;
        return true;
        """,
        [name, EXTENSION_ID],
    )
    return bool(result)


def select_page(client: Any, name: str, timeout: float = 15.0) -> bool:
    """Focus the tab whose URL ends in ``name`` and return whether it loaded."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            _content(client)
            for handle in client.window_handles:
                try:
                    client.switch_to_window(handle)
                    if (
                        name in client.get_url()
                        and client.execute_script("return document.readyState") == "complete"
                    ):
                        return True
                except Exception:  # noqa: BLE001 - the tab may still be loading
                    continue
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.3)
    return False


def close_page(client: Any, name: str) -> None:
    """Close every extension tab whose URL contains ``name``."""
    try:
        _chrome(client)
        client.execute_script(
            """
            const needle = arguments[0];
            for (const tab of [...gBrowser.tabs]) {
              try {
                if (tab.linkedBrowser.currentURI.spec.includes(needle)) {
                  gBrowser.removeTab(tab);
                }
              } catch (error) {}
            }
            """,
            script_args=[name],
        )
    except Exception:  # noqa: BLE001
        pass


def page_state(client: Any) -> dict[str, Any]:
    """The popup's visible view and the selectors the caller may click."""
    try:
        _content(client)
        state = client.execute_script(
            """
            const query = (selector) => document.querySelector(selector);
            const display = (selector) => {
              const element = query(selector);
              return element ? getComputedStyle(element).display : null;
            };
            const shown = (selector) => display(selector) !== "none";
            return {
              url: location.href,
              spinner: display("#spinner"),
              logged: display("#logged-view"),
              signin: display("#sign-in-view"),
              connected: shown(".disconnection-button"),
              disconnected: shown(".quick-connect-button"),
              status: query("#status") ? query("#status").innerText.trim() : "",
            };
            """
        )
        return state if isinstance(state, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def click(client: Any, selector: str) -> bool:
    """Click the first matching element inside the current extension page."""
    try:
        _content(client)
        return bool(
            client.execute_script(
                """
                const element = document.querySelector(arguments[0]);
                if (!element) return false;
                element.click();
                return true;
                """,
                script_args=[selector],
            )
        )
    except Exception:  # noqa: BLE001
        return False


def click_country(client: Any, code: str) -> bool:
    """Click the country row in the popup's server list."""
    try:
        _content(client)
        return bool(
            client.execute_script(
                """
                const name = document.querySelector(
                  `.country-name[data-country-code="${arguments[0].toUpperCase()}"]`
                );
                const button = name && name.closest(".connect-option");
                if (!button) return false;
                button.click();
                return true;
                """,
                script_args=[code],
            )
        )
    except Exception:  # noqa: BLE001
        return False


def country_name(client: Any, code: str) -> str:
    """The popup's English label for a country code (empty when not listed)."""
    try:
        _content(client)
        name = client.execute_script(
            """
            const node = document.querySelector(
              `.country-name[data-country-code="${arguments[0].toUpperCase()}"]`
            );
            return node ? node.innerText.trim() : "";
            """,
            script_args=[code],
        )
        return str(name or "")
    except Exception:  # noqa: BLE001
        return ""


def wait_popup(client: Any, timeout: float = 20.0) -> dict[str, Any]:
    """Wait until the popup has chosen a view (#spinner is gone)."""
    deadline = time.monotonic() + timeout
    state: dict[str, Any] = {}
    while time.monotonic() < deadline:
        state = page_state(client)
        if state.get("spinner") == "none" and (
            state.get("logged") == "block" or state.get("signin") == "block"
        ):
            return state
        time.sleep(0.3)
    return state


def read_local(client: Any, keys: list[str]) -> dict[str, Any]:
    """Read extension local storage, unwrapping StructuredCloneHolders."""
    try:
        raw = _async_script(
            client,
            """
            const cb = arguments[arguments.length - 1];
            const done = arguments[0];
            const wanted = arguments[1];
            const { ExtensionStorage } = ChromeUtils.importESModule(
              "resource://gre/modules/ExtensionStorage.sys.mjs"
            );
            ExtensionStorage.get(done, wanted)
              .then((items) => {
                const out = {};
                for (const key of Object.keys(items || {})) {
                  const value = items[key];
                  out[key] =
                    value && typeof value.deserialize === "function"
                      ? value.deserialize(globalThis)
                      : value;
                }
                cb(JSON.stringify(out));
              })
              .catch(() => cb("{}"));
            """,
            [EXTENSION_ID, keys],
        )
        return json.loads(raw) if isinstance(raw, str) else {}
    except Exception:  # noqa: BLE001
        return {}


def read_session(client: Any, keys: list[str]) -> dict[str, Any]:
    """Read extension session storage (synchronous in Firefox)."""
    try:
        raw = _script(
            client,
            """
            const wanted = arguments[0];
            const policy = WebExtensionPolicy.getByID(arguments[1]);
            if (!policy || !policy.extension) return "{}";
            const { extensionStorageSession } = ChromeUtils.importESModule(
              "resource://gre/modules/ExtensionStorage.sys.mjs"
            );
            try {
              const items = extensionStorageSession.get(policy.extension, wanted);
              const out = {};
              for (const key of Object.keys(items || {})) {
                const value = items[key];
                out[key] =
                  value && typeof value.deserialize === "function"
                    ? value.deserialize(globalThis)
                    : value;
              }
              return JSON.stringify(out);
            } catch (error) {
              return "{}";
            }
            """,
            [keys, EXTENSION_ID],
        )
        return json.loads(raw) if isinstance(raw, str) else {}
    except Exception:  # noqa: BLE001
        return {}


def read_page_storage(client: Any, area: str, keys: list[str]) -> dict[str, Any]:
    """Read chrome.storage from the extension page currently in the content tab.

    JSON.stringify runs inside the page realm, so Firefox's cross-compartment
    wrappers do not turn the values into empty objects.
    """
    try:
        _content(client)
        raw = client.execute_async_script(
            """
            const cb = arguments[arguments.length - 1];
            const area = arguments[0];
            const wanted = arguments[1];
            const chromeApi = window.wrappedJSObject.chrome;
            if (!chromeApi || !chromeApi.storage || !chromeApi.storage[area]) {
              return cb("{}");
            }
            chromeApi.storage[area].get(wanted, (items) => cb(JSON.stringify(items || {})));
            """,
            [area, keys],
        )
        return json.loads(raw) if isinstance(raw, str) else {}
    except Exception:  # noqa: BLE001
        return {}


def connected_server(client: Any) -> dict[str, Any]:
    """The extension's session-storage record for the connected server."""
    data = read_page_storage(client, "session", ["bex-connectedServer"])
    entry = data.get("bex-connectedServer")
    if not isinstance(entry, dict):
        entry = read_session(client, ["bex-connectedServer"]).get("bex-connectedServer")
    return entry if isinstance(entry, dict) else {}


def connected_value(client: Any) -> dict[str, Any]:
    """The ``value`` of the connected-server record (empty when disconnected)."""
    value = connected_server(client).get("value")
    return value if isinstance(value, dict) else {}
