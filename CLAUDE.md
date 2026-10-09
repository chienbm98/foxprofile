# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

FoxProfile is a Python 3.10+ manager for [Camoufox](https://github.com/daijro/camoufox) anti-detect browser profiles: a Flet desktop UI, a FastAPI REST API + single-file web panel, and an MCP server for AI agents.

## Commands

```bash
pip install -r requirements-dev.txt     # dev deps (runtime deps live in requirements.txt)
python -m camoufox fetch                # download the browser; needed only to actually launch profiles

python -m src.main                      # desktop app + API on 127.0.0.1:8000
python -m src.server [--port N] [--headed]   # API + web panel at /, no desktop window, browsers hidden
python foxprofile_mcp.py                # MCP over stdio (client of a running API; FOXPROFILE_URL / FOXPROFILE_API_TOKEN)

ruff check src tests chrome_engine
ruff format --check src tests chrome_engine
pytest                                  # tests + chrome_engine/tests; real-browser tests skip unless fetched
pytest tests/test_validation.py::test_parse_proxy_with_auth   # single test
```

CI (`.github/workflows/ci.yml`) runs lint plus pytest on Windows/macOS/Linux × Python 3.10/3.12. `tests/e2e/*.py` are manual scripts against a real FoxProfile (browser + network) and are not part of pytest; see `tests/e2e/README.md`, and point them at a scratch `FOXPROFILE_DATA_DIR` / `FOXPROFILE_PROFILES_FILE`.

Run everything from the repo root: `profiles.json`, `camoufox_data/`, `logs/` and `.env` are resolved relative to the working directory.

## Architecture

**One `Container`, two front ends.** `src/core/container.py` lazily builds the services (`ProfileManager`, `BrowserLauncher`, `ProxyService`, `EventBus`). In desktop mode (`src/main.py`) the FastAPI app runs in a background thread of the same process as the Flet UI and shares that container. The UI calls services directly; API routes that mutate state call `event_bus.emit()` so the desktop UI refreshes. Server mode (`src/server.py`) builds the same container with no UI.

**Each browser is a subprocess.** `BrowserLauncher` (`services/browser/launcher.py`) spawns `services/browser/runner.py` per profile and reads a line protocol from its stdout: `CONTROL:<port>:<token>`, then `BROWSER_STARTED`, `BROWSER_CLOSED`, `LAUNCH_FAILED: ...`. `CONTROL` must be printed before `BROWSER_STARTED`. The runner hosts an aiohttp control server (`control.py`) on loopback with a per-launch token; the API's page-control routes (`api/routes/page.py`) forward through `BrowserLauncher.control()` to it. `control.py` also enforces the URL scheme allow-list (`http`, `https`, `about` only).

**Two engines.** `Profile.engine` is `camoufox` (default) or `chrome`, fixed at creation. `process.runner_command` starts `services/browser/runner.py` or `python -m chrome_engine.runner`; both print the same protocol and share `control.py`/`session.py`. `chrome_engine/` (fingerprint-chromium driven by Playwright) keeps its persona in `chrome_persona.json`, which `fingerprint.summary/reset` also handle. Its browser build is downloaded on demand: creating a Chrome profile starts a background download (`services/browser/chrome_prefetch.py`), and the Chrome runner installs it on launch if still missing (`chrome_engine.runner.ensure_installed`, progress printed to the log). `chrome_engine/fetch.install` is safe across processes: per-PID `.part` files, a second process waits for a live download instead of fetching twice, and a finished install is never replaced. `python -m chrome_engine fetch` still works by hand. Its tests live in `chrome_engine/tests` (browser tests skip unless fetched).

**Stopped-profile operations** (cookie export/import) run `services/browser/cookie_tool.py` as its own headless Camoufox subprocess (last stdout line `RESULT:<json>`). They hold `BrowserLauncher.exclusive(name)`, which refuses launches while the data dir is in use and raises `ProfileBusyError` if the profile is running.

**Fingerprints** are generated once and persisted as `camoufox_data/<profile>/fingerprint.json` (`services/browser/fingerprint.py`); runner and cookie_tool both load it so a profile always presents the same device. Timezone/locale follow the proxy's exit IP via Camoufox geoip unless pinned per profile (`runner.geo_overrides`); `services/proxy/geo_check.py` implements "Check IP". Open tabs are snapshotted every 2 s to `camoufox_data/<profile>/tabs.json` (`services/browser/session.py`) and reopened by the runner on launch; the snapshot loop must not save an empty list, because the last tab closing is how a user ends the session.

**MCP is a REST client.** `src/mcp_server/server.py` defines the tools with FastMCP and calls the REST API over HTTP. The same tools are also served over Streamable HTTP at `/mcp` (`api/mcp_http.py`), calling back into the API through `self_url` on loopback. A new capability therefore usually needs a REST route first, then an MCP tool. MCP deliberately has no delete tool.

**Auth.** `FOXPROFILE_API_TOKEN` protects the REST routers, the web panel and `/mcp` (`/health` and `/info` stay public). `check_bind_safety` refuses to start on a non-loopback host without a 24+ character token. Without a token, `LocalOnlyGuard` blocks CSRF/DNS-rebinding requests from websites.

**Config** is read from `FOXPROFILE_*` env vars (and `.env`) at import time in `src/core/config.py`. Anything that must change it, like server mode defaulting `FOXPROFILE_HEADLESS=true`, has to set the env var before `src.core.config` is imported; runner subprocesses inherit it through the environment.

**UI.** The web panel is one static file, `src/web/index.html` (no build step, no external requests), served at `/`; its design tokens are the CSS custom properties in `:root` and its strings live in its own `I18N` object (vi + en), not in `strings.py`. Fonts (Be Vietnam Pro, JetBrains Mono, OFL) ship in `src/assets/fonts/` and are served publicly at `/assets/fonts/{name}` for the panel and registered by `theme/page.py` for Flet (one family per weight, since Flet maps one file per family). The Flet app is `src/ui/`: `theme/colors.py` (`COLORS` + font family constants) and `theme/styles.py` hold the tokens; `App._build_ui()` builds every control and is called again by `_set_language()`, because `strings.set_language()` only changes what `get_string` returns for controls built afterwards. Profile rows share one column grid (`profile_card.COLUMNS`) with the header row.

## Conventions

- UI strings are never hard-coded: add the key to **both** `en` and `vi` in `src/core/strings.py` and use `get_string("key")`. `tests/test_strings.py` fails if a key is missing in either language.
- UI work: read `DESIGN.md` (visual system) and `PRODUCT.md` (users, constraints) first. Use the tokens (`COLORS` keys, CSS custom properties), never new hex values. Fox orange is only for things you can press; Stop is ink, not red. Status reads by form as well as colour (live = violet double-rule stamp, starting = grey single rule, failed = struck red single rule). Every data cell in a profile row keeps two lines. Change the desktop app and the web panel together so both surfaces stay one product.
- In Vietnamese copy, keep industry terms in English: profile, proxy, cookie, fingerprint, engine, timezone, locale, headless, API, MCP.
- Profile names become directory names: always pass them through `validate_profile_name`.
- Proxies go through `utils/proxy_parser.parse_proxy` (accepts `[scheme://][user:pass@]host:port` and `host:port:user:pass`); validation is `utils/validation.validate_proxy_format`.
- `README.md` (Vietnamese, primary) and `README.en.md` must stay in sync. `CONTRIBUTING.md`, `SECURITY.md` and `docs/DEPLOY.md` are in Vietnamese.
- Release: bump `version` in `pyproject.toml`, `VERSION` in `src/api/app.py`, and `CHANGELOG.md` in one PR, then tag `vX.Y.Z`.
- `main` is protected: changes go through a PR with all CI checks green. Commits follow Conventional Commits.
- Never commit `profiles.json`, `camoufox_data/`, `logs/` or `.env`; they hold real cookies and proxy credentials.
