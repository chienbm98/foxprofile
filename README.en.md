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
- Per-profile proxy (HTTP/HTTPS/SOCKS4/SOCKS5, with or without auth) and a proxy checker. Timezone and locale follow the IP.
- Cookie export/import: Cookie-Editor / EditThisCookie JSON (GoLogin, GPM, Multilogin, Cookie-Editor extension) and Netscape `cookies.txt` (yt-dlp, curl, wget).
- Profile export/import as ZIP, with or without browser data; the fingerprint always travels with the profile.
- Bulk launch, stop and delete.
- Search profiles by name or proxy; cards show the proxy (credentials hidden) and the emulated device.
- Local REST API with Swagger docs.

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

## Cookies and fingerprints

Click the 🍪 icon on a profile card. The profile's browser must be stopped: FoxProfile opens the profile headless to read and write cookies.

- Imported session cookies are given a one-year lifetime; otherwise Firefox would discard them when the browser closes.
- "New fingerprint" deletes the stored fingerprint so the next launch presents a different device. Changing a profile's OS also regenerates it.

## Configuration

Copy `.env.example` to `.env` to override defaults. Variables use the `FOXPROFILE_` prefix (`LANG`, `PROFILES_FILE`, `DATA_DIR`, `LOG_DIR`, `LOG_LEVEL`, `PROXY_TIMEOUT`, `LAUNCH_TIMEOUT`, `API_HOST`, `API_PORT`).

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

> ⚠️ The API has **no authentication**. Keep it bound to `127.0.0.1`; anyone who can reach it can control every profile and read every cookie.

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

[MIT](LICENSE). Copyright (c) 2026 chienbm98.
