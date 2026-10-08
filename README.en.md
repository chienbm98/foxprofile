<div align="center">
  <img src="src/assets/icon.png" width="112" alt="FoxProfile logo" />
  <h1>FoxProfile</h1>
  <p><strong>Free, open-source manager for anti-detect browser profiles</strong></p>
  <p>Per-profile device fingerprint, cookies and proxy · Vietnamese and English UI · Local REST API</p>
  <p><a href="README.md">Tiếng Việt</a> · English</p>
</div>

![FoxProfile](docs/images/main.png)

FoxProfile is a desktop manager for [Camoufox](https://github.com/daijro/camoufox) profiles, a Firefox build that spoofs device fingerprints at the engine level. It is a self-hosted alternative to paid anti-detect browsers such as GoLogin, GPM or MoreLogin.

## Features

- Persistent per-profile fingerprint, with a one-click "new fingerprint" reset.
- Per-profile proxy (HTTP/HTTPS/SOCKS4/SOCKS5, with or without auth) and a proxy checker. Timezone and locale follow the IP or can be pinned per profile; **Check IP** compares the exit IP across Cloudflare, ipinfo and ip-api and warns about country/timezone mismatches and datacenter IPs.
- Cookie export/import: Cookie-Editor / EditThisCookie JSON (GoLogin, GPM, Multilogin, Cookie-Editor extension) and Netscape `cookies.txt` (yt-dlp, curl, wget).
- Profile export/import as ZIP, with or without browser data; the fingerprint always travels with the profile.
- Bulk launch, stop and delete.
- Search profiles by name or proxy; cards show the proxy (credentials hidden) and the emulated device.
- MCP server so AI agents (Claude, Cursor...) can launch profiles and browse, click, type and take screenshots.
- Server mode with a token-protected web panel and remote screen view, for VPS deployments.
- REST API with Swagger docs.

## Install

Python 3.10+.

```bash
git clone https://github.com/chienbm98/foxprofile.git
cd foxprofile
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux/macOS
pip install -r requirements.txt
python -m camoufox fetch
```

## Run

```bash
python -m src.main
```

On Windows you can also run `run_foxprofile.bat`. The API listens on `http://127.0.0.1:8000`; docs are at `/docs`. Set `FOXPROFILE_LANG=en` for the English UI.

## Timezone, language and Check IP

By default, every launch looks up the exit IP (through the profile's proxy) and sets the timezone, language, geolocation and WebRTC IP from it. Worth knowing:

- **The automatic language is drawn at random on every launch**, weighted by how many people speak each language in the IP's country. A French IP gives `fr-FR` roughly 60% of the time and `en-FR`, `es-FR`… otherwise. An account whose language changes between sessions looks suspicious, so pin the language per profile.
- **GeoIP databases disagree.** Cloudflare may place an IP in one country and Google in another, and Camoufox may pick a same-offset timezone with a different name (a Vietnamese IP gets `Asia/Bangkok` rather than `Asia/Ho_Chi_Minh`).
- **Datacenter IPs get captchas** whatever the browser looks like. For Cloudflare-protected sites a residential or mobile proxy matters more than any other setting.

The profile dialog has **Timezone** (IANA name, e.g. `Asia/Ho_Chi_Minh`) and **Language** (e.g. `vi-VN`) fields; blank means follow the IP. **Check IP** resolves the exit IP through the proxy, compares it with Cloudflare, ipinfo and ip-api, and warns about country or timezone mismatches, datacenter IPs, proxies that leave over different IPv4/IPv6 addresses, and a language left on random.

## Server mode and web panel (VPS)

No desktop window: API + web panel only, browsers run hidden.

```bash
python -m src.server                     # http://127.0.0.1:8000
python -m src.server --host 0.0.0.0      # exposed: FOXPROFILE_API_TOKEN is required
```

Open `http://<host>:8000/` for the **web panel**: create, edit, launch and stop profiles, move cookies, and **view a profile's screen remotely**. Click on the screenshot and type to log in or solve a captcha even when the browser runs hidden on a server.

![Web panel](docs/images/panel.png)

When listening on anything but `127.0.0.1`, the server **refuses to start** without `FOXPROFILE_API_TOKEN` (24+ characters). The panel, the REST API and MCP share that token. Put the server behind an HTTPS reverse proxy (Caddy, Nginx) on a VPS. On a display-less Linux box, `FOXPROFILE_HEADLESS=virtual` (needs `xvfb`) runs browsers on a virtual display, which is harder to detect than plain headless.

## MCP: let AI agents drive the browser

FoxProfile ships an MCP server so Claude Code, Claude Desktop, Cursor, VS Code and others can manage profiles and act on pages (navigate, read, click, type, screenshot).

**Quickest:** click **🤖 Connect AI (MCP)** in the desktop app or the web panel. It generates ready-to-paste configs for each AI app with your address and token; copy and paste.

![Connect AI (MCP)](docs/images/mcp-guide.png)

MCP is served over HTTP at `/mcp` on FoxProfile's own port, so it also works when FoxProfile runs on a VPS:

```bash
claude mcp add --transport http foxprofile http://127.0.0.1:8000/mcp
claude mcp add --transport http foxprofile https://your-vps/mcp --header "Authorization: Bearer <token>"
```

Claude Desktop only launches local MCP servers: use `foxprofile_mcp.py` on the same machine, or the `npx mcp-remote` bridge from another one. The Connect AI dialog generates both.

Tools: profile management (`list_profiles`, `create_profile`, `launch_profile`, `stop_profile`...), cookies and fingerprints, `check_profile_ip`, page control (`browser_navigate`, `browser_snapshot`, `browser_click`, `browser_click_at`, `browser_type`, `browser_press`, `browser_wait_for`, `browser_screenshot`, `browser_evaluate`) and tabs. There is deliberately no delete tool, and only `http`, `https` and `about:blank` can be opened.

## Cookies and fingerprints

Click the 🍪 icon on a profile card. The profile's browser must be stopped: FoxProfile opens the profile headless to read and write cookies.

- Imported session cookies are given a one-year lifetime; otherwise Firefox would discard them when the browser closes.
- "New fingerprint" deletes the stored fingerprint so the next launch presents a different device. Changing a profile's OS also regenerates it.

## Configuration

Copy `.env.example` to `.env` to override defaults. Variables use the `FOXPROFILE_` prefix (`LANG`, `PROFILES_FILE`, `DATA_DIR`, `LOG_DIR`, `LOG_LEVEL`, `PROXY_TIMEOUT`, `LAUNCH_TIMEOUT`, `API_HOST`, `API_PORT`, `HEADLESS`, `API_TOKEN`).

## REST API

Prefix `/api/v1`.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Health check |
| `GET` / `POST` | `/profiles` | List / create profiles |
| `GET` / `PATCH` / `DELETE` | `/profiles/{name}` | Read / update / delete a profile |
| `POST` | `/profiles/{name}/export` | Export a profile to ZIP |
| `POST` | `/profiles/import` | Import a profile from ZIP |
| `GET` | `/profiles/{name}/cookies?format=json\|netscape` | Export cookies |
| `POST` | `/profiles/{name}/cookies` | Import cookies (`{"content": "<JSON or cookies.txt>"}`) |
| `GET` / `DELETE` | `/profiles/{name}/fingerprint` | Show / reset the fingerprint |
| `GET` | `/browser` | Running profiles |
| `POST` | `/browser/{name}/launch` | Launch; waits for ready (`200`) or failure (`502`). `?wait=false` returns `202` immediately |
| `POST` | `/browser/{name}/stop` | Stop |
| `POST` | `/proxy/check` | Check a proxy |
| `GET` | `/profiles/{name}/ip-check` | Where Cloudflare/ipinfo/ip-api place the profile's exit IP, with mismatch warnings |
| `POST` | `/proxy/geo-check` | Same for an unsaved `{proxy, timezone, locale}` |
| `POST`/`GET` | `/browser/{name}/page/...` | Page control: `navigate`, `back`, `snapshot`, `text`, `click`, `click-at`, `type`, `keyboard`, `press`, `wait`, `screenshot`, `evaluate`, `tabs` |

With `FOXPROFILE_API_TOKEN` set, every request except `/health` and `/info` needs `Authorization: Bearer <token>`.

## Data layout

```text
profiles.json                                  profile list
camoufox_data/<profile>/                       browser data (cookies, history, storage)
camoufox_data/<profile>/fingerprint.json       the profile's device fingerprint
logs/foxprofile_YYYYMMDD.log                   daily log
```

`camoufox_data/` holds the login cookies of every account. Never commit or share it.

## Responsible use

Anti-detect browsers are legitimate tools for privacy, web testing and agencies managing client accounts. Running multiple accounts on one platform may still violate the terms of Facebook, TikTok, Google, Shopee and others. You are responsible for how you use this software.

## License

[MIT](LICENSE). Copyright (c) 2026 chienbm98; Copyright (c) 2025-2026 Vladislav Zenkevich.

## Acknowledgements

FoxProfile grew out of **CamouMgr** by Vladislav Zenkevich (MIT) and is built on the [Camoufox](https://github.com/daijro/camoufox) browser by daijro.
