<div align="center">
  <img src="src/assets/icon.png" width="112" alt="FoxProfile logo" />
  <h1>FoxProfile</h1>
  <p><strong>免费开源的反检测浏览器 profile 管理器</strong></p>
  <p>每个 profile 拥有独立的设备 fingerprint、cookie 和 proxy · 两种 engine：Camoufox (Firefox) 与 Chrome · 英文与简体中文界面 · 提供 REST API 与 MCP 以便自动化</p>

  <p>
    <a href="https://github.com/chienbm98/foxprofile/actions/workflows/ci.yml"><img src="https://github.com/chienbm98/foxprofile/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
    <a href="https://github.com/chienbm98/foxprofile/releases/latest"><img src="https://img.shields.io/github/v/release/chienbm98/foxprofile" alt="Release" /></a>
    <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+" />
    <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey" alt="Windows | macOS | Linux" />
    <a href="LICENSE"><img src="https://img.shields.io/github/license/chienbm98/foxprofile" alt="MIT License" /></a>
    <a href="https://buymeacoffee.com/chienbm98"><img src="https://img.shields.io/badge/Buy%20me%20a%20coffee-%E2%98%95-FFDD00?logo=buymeacoffee&logoColor=black" alt="Buy me a coffee" /></a>
  </p>

  <p><a href="README.md">English</a> · 简体中文</p>
  <p>
    <a href="#快速开始">快速开始</a> ·
    <a href="#功能">功能</a> ·
    <a href="#rest-api">REST API</a> ·
    <a href="#mcp让-ai-操控浏览器">MCP</a> ·
    <a href="#参与贡献">参与贡献</a>
  </p>
</div>

![FoxProfile](docs/images/en/main.png)

FoxProfile 用来管理反检测浏览器 profile：每个 profile 都是一个独立的身份，拥有自己的设备 fingerprint、cookie、proxy、timezone 和 locale。默认浏览器是 [Camoufox](https://github.com/daijro/camoufox)，一个在引擎层伪装 fingerprint 的 Firefox 构建；另外还提供基于 [fingerprint-chromium](https://github.com/adryfish/fingerprint-chromium) 的实验性 Chrome engine。它是 GoLogin、GPM、MoreLogin 等付费反检测浏览器的自托管替代方案，可以运行在你自己的电脑或 VPS 上。

## 目录

- [功能](#功能)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [Timezone、locale 与 Check IP](#timezonelocale-与-check-ip)
- [Server 模式与 web panel](#server-模式与-web-panel)
- [MCP：让 AI 操控浏览器](#mcp让-ai-操控浏览器)
- [Chrome engine（实验性）](#chrome-engine实验性)
- [Cookie 与 fingerprint](#cookie-与-fingerprint)
- [配置](#配置)
- [REST API](#rest-api)
- [开发](#开发)
- [参与贡献](#参与贡献)
- [支持](#支持)
- [使用须知](#使用须知)
- [许可证](#许可证)
- [致谢](#致谢)

## 功能

- **每个 profile 持久保存的 fingerprint。** 首次启动时生成一台设备（屏幕、GPU、CPU 核数、字体、canvas/audio 噪声）并保存下来；之后的启动都沿用同一台设备。需要时可以随时重新生成。
- **两种 engine。** Camoufox (Firefox，默认) 或 Chrome (fingerprint-chromium，实验性)，在创建 profile 时选择。需要时会自动下载 Chrome 构建。
- **会话保持。** 历史记录、cookie 和登录状态都保存在 profile 目录中；上次打开的标签页会在下次启动时重新打开。
- **每个 profile 独立的 proxy**：支持 HTTP/HTTPS/SOCKS4/SOCKS5，可带或不带认证，也支持 `host:port:user:pass` 格式，并附带 proxy 检测。
- **Timezone 与 locale** 可跟随出口 IP，也可以为每个 profile 固定。**Check IP** 会对比 Cloudflare、ipinfo 和 ip-api 给出的出口 IP 信息，并在国家/timezone 不一致或使用机房 IP 时给出警告。
- **Cookie 导出/导入**：支持 Cookie-Editor / EditThisCookie JSON（GoLogin、GPM、Multilogin、Cookie-Editor 扩展）以及 Netscape `cookies.txt`（yt-dlp、curl、wget）。
- **Profile 导出/导入**：打包为 ZIP，可选是否包含浏览器数据，用于在机器之间迁移 profile。fingerprint 始终随 profile 一起迁移。
- **便于快速浏览的 profile 表格**：每一行显示 engine、模拟的设备、proxy（隐藏凭据）、timezone/locale 以及状态。状态不仅颜色不同，形状也不同：带启动时间的紫色双线印章表示运行中，灰色线框表示启动中，带删除线的红色印章表示启动失败。
- **筛选与搜索**：可按运行中、有/无 proxy、Chrome engine 筛选（附数量）；可按名称或 proxy 搜索。
- **批量操作**：一次启动、停止或删除多个 profile。
- **MCP server**：让 AI agent（Claude、Cursor 等）能够启动 profile、浏览网页、点击、输入和截图。
- **Server 模式 + web panel**：适用于 VPS 部署，可远程管理 profile 并查看其屏幕，由 token 保护。
- **REST API**：附带 Swagger 文档，便于脚本调用。
- **英文**（默认）与简体中文界面，可在应用内切换。字体已内置，无需联网。

## 环境要求

- Python 3.10+
- Windows、macOS 或 Linux（CI 三者都会测试）
- 为 Camoufox 和 GeoIP 数据库预留几百 MB 磁盘空间；如果使用 Chrome engine，另需约 140-190 MB

## 快速开始

```bash
git clone https://github.com/chienbm98/foxprofile.git
cd foxprofile

python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux/macOS

pip install -r requirements.lock
python -m camoufox fetch
```

`camoufox fetch` 会从 Camoufox 的 GitHub releases 下载 Camoufox 浏览器（几百 MB）。第一次启动 profile 时还会下载一个 GeoIP 数据库（约 50 MB）。

运行应用：

```bash
python -m src.main
```

在 Windows 上也可以双击 `run_foxprofile.bat`。应用会打开管理窗口，并在 `http://127.0.0.1:8000` 提供 API；API 文档位于 `http://127.0.0.1:8000/docs`。设置 `FOXPROFILE_LANG=zh-CN` 即可使用简体中文界面。

## Timezone、locale 与 Check IP

默认情况下，每次启动 Camoufox 都会（通过该 profile 的 proxy）查询出口 IP，并据此设置 timezone、locale、地理位置和 WebRTC IP。需要了解的几点：

- **自动 locale 每次启动都是随机抽取的**，按该 IP 所在国家各语言的使用人数加权。法国 IP 大约 60% 的情况下得到 `fr-FR`，其余是 `en-FR`、`es-FR` 等。账号的语言在不同会话之间变来变去会显得可疑，所以请为每个 profile 固定 locale。
- **各家 GeoIP 数据库并不一致。** Cloudflare 可能把一个 IP 判定在某个国家，Google 则判定在另一个国家；Camoufox 也可能选中偏移量相同但名称不同的 timezone（越南 IP 会得到 `Asia/Bangkok` 而不是 `Asia/Ho_Chi_Minh`）。
- **机房 IP 无论浏览器看起来多像真人都会遇到验证码。** 对于受 Cloudflare 保护的网站，住宅或移动 proxy 比其他任何设置都重要。

![创建 profile 对话框](docs/images/en/profile-dialog.png)

Profile 对话框中有 **Timezone**（IANA 名称，例如 `Asia/Ho_Chi_Minh`）和 **Locale**（例如 `vi-VN`）两个字段；留空表示跟随 IP。**Check IP** 会通过 proxy 解析出口 IP，与 Cloudflare、ipinfo 和 ip-api 对比，并对以下情况给出警告：国家或 timezone 不一致、机房 IP、proxy 的 IPv4/IPv6 出口地址不同，以及 locale 仍为随机。

## Server 模式与 web panel

没有桌面窗口：只提供 API + web panel，浏览器隐藏运行。适合 VPS。

```bash
python -m src.server                     # http://127.0.0.1:8000
python -m src.server --host 0.0.0.0      # 对外暴露：必须设置 FOXPROFILE_API_TOKEN
```

打开 `http://<host>:8000/` 即可使用 **web panel**：与桌面应用相同的 profile 表格、筛选和批量操作；可以创建、编辑、启动和停止 profile，迁移 cookie，并**远程查看 profile 的屏幕**。即使浏览器在服务器上隐藏运行，也可以点击截图并输入文字来登录或通过验证码。

| Web panel | 远程查看屏幕 |
| --- | --- |
| ![Web panel](docs/images/en/panel.png) | ![远程查看屏幕](docs/images/en/panel-viewer.png) |

**安全：** 当监听的地址不是 `127.0.0.1` 时，如果没有设置 `FOXPROFILE_API_TOKEN`（至少 24 个字符），server 会**拒绝启动**。Panel、REST API 和 MCP 共用同一个 token。

```bash
# 生成随机 token
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

在 VPS 上，请把 server 放在 HTTPS 反向代理（Caddy、Nginx）之后，避免 token 以明文传输。在没有显示器的 Linux 机器上，`FOXPROFILE_HEADLESS=virtual`（需要 `xvfb`）会让浏览器运行在虚拟显示器上，比普通 headless 更难被检测。

完整部署指南（Ubuntu、systemd、nginx、HTTPS；中文）：[docs/DEPLOY.md](docs/DEPLOY.md)。

## MCP：让 AI 操控浏览器

FoxProfile 内置 MCP server，Claude Code、Claude Desktop、Cursor、VS Code 等都可以通过它管理 profile 并操作网页：导航、读取、点击、输入、截图。

**最快的方式：** 在桌面应用或 web panel 的左侧栏点击 **Connect AI (MCP)**。它会为每个 AI 应用生成可直接粘贴的配置，其中已填好你的地址和 token。

![Connect AI (MCP)](docs/images/en/mcp-guide.png)

MCP 通过 HTTP 在 FoxProfile 自身端口的 `/mcp` 路径提供服务，因此 FoxProfile 运行在 VPS 上时同样可用：

```bash
# Claude Code
claude mcp add --transport http foxprofile http://127.0.0.1:8000/mcp
# 带 token 的 server：
claude mcp add --transport http foxprofile https://your-vps.example.com/mcp --header "Authorization: Bearer <token>"
```

```jsonc
// Cursor: ~/.cursor/mcp.json
{ "mcpServers": { "foxprofile": { "url": "http://127.0.0.1:8000/mcp" } } }
```

Claude Desktop 只能启动本地 MCP server：在同一台机器上使用 `foxprofile_mcp.py`，从其他机器连接则使用 `npx mcp-remote` 桥接。Connect AI 对话框两种配置都会生成。

然后直接提问即可，例如：*“打开 profile tiktok-us-02，访问 tiktok.com，并给我发一张截图”*。

| 分组 | 工具 |
| --- | --- |
| Profiles | `list_profiles`, `get_profile`, `create_profile`, `update_profile`, `launch_profile`, `stop_profile`, `running_profiles` |
| Cookies & fingerprints | `import_cookies`, `get_fingerprint`, `reset_fingerprint`, `check_proxy`, `check_profile_ip` |
| 页面 | `browser_navigate`, `browser_back`, `browser_snapshot`, `browser_get_text`, `browser_click`, `browser_click_at`, `browser_type`, `browser_press`, `browser_wait_for`, `browser_screenshot` |
| 标签页 | `browser_tabs`, `browser_tab_new`, `browser_tab_select`, `browser_tab_close` |

这里**刻意没有**提供删除工具，以免 agent 误删某个账号的 cookie。只能打开 `http`、`https` 和 `about:blank`；`file://` 和 `about:config` 会被拦截。

## Chrome engine（实验性）

除了 Camoufox (Firefox)，profile 也可以运行在 **Chrome** engine 上：这是一个在 C++ 层打补丁伪装 fingerprint 的 Chromium 构建（[fingerprint-chromium](https://github.com/adryfish/fingerprint-chromium)，BSD-3 许可证）。创建 profile 时在 **Engine** 中选择；创建之后不能更改。浏览器构建（约 140-190 MB，取决于操作系统，从 fingerprint-chromium 的 GitHub releases 获取并校验 SHA-256）会在创建第一个 Chrome profile 时立即在后台下载，如果启动时仍缺失则会在启动时下载；进度显示在日志中。如需提前下载：`python -m chrome_engine fetch`。

请选择与运行 FoxProfile 的机器相同的操作系统：其他操作系统的 persona 会泄露本机的字体，而在 Windows/macOS 上使用 Linux persona 会被拒绝，因为 WebGL 会暴露真实 GPU。支持：Windows x64、macOS Apple Silicon、Linux x64（未测试）。Fingerprint 选项卡对 Chrome profile 同样可用，但只提供浏览器能够实现的模式（CPU 核数、GPU、audio、WebRTC、timezone、语言、地理位置以及本地网络扫描防护）；它做不到的项目，例如 user agent、屏幕和字体，会显示为不支持。Chrome 上的 canvas 始终是真实的：该构建的 canvas 噪声会让 `measureText()` 返回约 0（fingerprint-chromium#96）。详情与测试结果（中文）：[chrome_engine/README.md](chrome_engine/README.md)。

## Cookie 与 fingerprint

![Cookies & fingerprint](docs/images/en/cookies.png)

点击 profile 行上的 cookie 按钮即可打开 **Cookies & fingerprint**。**该 profile 的浏览器必须处于停止状态**：FoxProfile 会以 headless 方式打开该 profile 来读写 cookie。

- 导入的 session cookie 会被设置为一年有效期；否则浏览器关闭时会丢弃它们。
- “New fingerprint” 会删除已保存的 fingerprint，使下次启动呈现为另一台设备。更改 profile 的操作系统也会重新生成。

## 配置

所有配置都是可选的。如需覆盖默认值，把 `.env.example` 复制为 `.env`。

| 变量 | 默认值 | 含义 |
| --- | --- | --- |
| `FOXPROFILE_LANG` | `en` | 界面语言：`en` 或 `zh-CN` |
| `FOXPROFILE_PROFILES_FILE` | `profiles.json` | Profile 列表文件 |
| `FOXPROFILE_DATA_DIR` | `camoufox_data` | 数据目录，每个 profile 一个子目录 |
| `FOXPROFILE_LOG_DIR` | `logs` | 日志目录 |
| `FOXPROFILE_LOG_LEVEL` | `INFO` | 日志级别 |
| `FOXPROFILE_PROXY_TIMEOUT` | `10` | Proxy 检测超时（秒） |
| `FOXPROFILE_LAUNCH_TIMEOUT` | `90` | API 等待浏览器启动完成的时间（秒） |
| `FOXPROFILE_HEADLESS` | `false`（server 模式下为 `true`） | 隐藏浏览器：`true`、`false` 或 `virtual`（Linux + Xvfb） |
| `FOXPROFILE_RESTORE_TABS` | `true` | 重新打开上次运行时的标签页 |
| `FOXPROFILE_API_TOKEN` | *(空)* | API、web panel 和 MCP 使用的 token。当 API 监听 `127.0.0.1` 之外的地址时必须设置 |
| `FOXPROFILE_API_HOST` | `127.0.0.1` | API 主机 |
| `FOXPROFILE_API_PORT` | `8000` | API 端口 |

### Proxy 格式

`host:port`、`http://host:port`、`https://...`、`socks4://...`、`socks5://...`，可选带 `user:pass@`。服务商常用的 `host:port:user:pass` 格式也支持。留空表示直连。

### 数据目录结构

```text
profiles.json                                  profile 列表（名称、engine、proxy、OS、timezone、locale）
camoufox_data/<profile>/                       浏览器数据：cookie、历史记录、localStorage
camoufox_data/<profile>/fingerprint.json       设备 fingerprint（Camoufox engine）
camoufox_data/<profile>/chrome_persona.json    设备 fingerprint（Chrome engine）
camoufox_data/<profile>/tabs.json              下次启动时要重新打开的标签页
logs/foxprofile_YYYYMMDD.log                   每日日志
```

> [!WARNING]
> `camoufox_data/` 中保存着所有账号的登录 cookie。切勿提交或分享。

## REST API

前缀为 `/api/v1`。应用运行时，完整参考文档位于 `/docs`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 健康检查 |
| `GET` / `POST` | `/profiles` | 列出 / 创建 profile |
| `GET` / `PATCH` / `DELETE` | `/profiles/{name}` | 读取 / 更新 / 删除 profile（`engine` 不可更改） |
| `GET` | `/profiles/{name}/data-dir` | Profile 数据目录的路径 |
| `POST` | `/profiles/{name}/export` | 将 profile 导出为 ZIP |
| `POST` | `/profiles/import` | 从 ZIP 导入 profile |
| `GET` | `/profiles/{name}/cookies?format=json\|netscape` | 导出 cookie |
| `POST` | `/profiles/{name}/cookies` | 导入 cookie（`{"content": "<JSON 或 cookies.txt>"}`） |
| `GET` / `DELETE` | `/profiles/{name}/fingerprint` | 查看 / 生成新的 fingerprint |
| `GET` | `/profiles/{name}/ip-check` | Cloudflare/ipinfo/ip-api 对该 profile 出口 IP 的定位结果，附不一致警告 |
| `GET` | `/browser` | 正在运行的 profile |
| `GET` | `/browser/{name}/status` | Profile 是否在运行 |
| `POST` | `/browser/{name}/launch` | 启动并等待就绪或失败（已在运行或忙碌时返回 409） |
| `POST` | `/browser/{name}/stop` | 停止 |
| `POST` | `/proxy/check` | 检测 proxy |
| `POST` | `/proxy/geo-check` | 与 `ip-check` 相同，但针对未保存的 `{proxy, timezone, locale}` |
| `POST` | `/browser/{name}/page/navigate` · `back` | 在当前标签页打开 URL、后退 |
| `GET` | `/browser/{name}/page/snapshot` · `text` | 页面的 accessibility tree（用于挑选 selector）、页面文本 |
| `POST` | `/browser/{name}/page/click` · `type` · `press` · `wait` | 点击、输入、按键、等待元素（Playwright selector） |
| `POST` | `/browser/{name}/page/click-at` · `keyboard` | 按坐标点击、向当前聚焦的元素输入 |
| `GET` | `/browser/{name}/page/screenshot` | 标签页的 PNG（`?format=json` 返回 base64） |
| `POST` | `/browser/{name}/page/evaluate` | 运行 JavaScript |
| `GET` / `POST` | `/browser/{name}/page/tabs` | 列出标签页 / 新开标签页 |
| `POST` / `DELETE` | `/browser/{name}/page/tabs/{index}/select` · `/page/tabs/{index}` | 选中 / 关闭标签页 |
| `GET` | `/mcp/setup?base_url=...` | 各 AI 应用的 MCP 配置（供 Connect AI 对话框使用） |

设置了 `FOXPROFILE_API_TOKEN` 后，除 `/health` 和 `/info` 外的所有请求都需要携带 `Authorization: Bearer <token>`。

示例：

```bash
# 创建一个带 proxy 的 macOS profile。使用 Chrome engine 时加上 "engine": "chrome"（默认是 "camoufox"）。
curl -X POST http://127.0.0.1:8000/api/v1/profiles \
  -H "Content-Type: application/json" \
  -d '{"name": "tiktok-us-02", "os_type": "macos", "proxy": "socks5://user:pass@203.0.113.10:1080"}'

# 启动。运行成功返回 200，失败返回 502 并附带原因。
# 加上 ?wait=false 可立即返回（202）。
curl -X POST http://127.0.0.1:8000/api/v1/browser/tiktok-us-02/launch

# 以 cookies.txt 格式导出 cookie
curl "http://127.0.0.1:8000/api/v1/profiles/tiktok-us-02/cookies?format=netscape" -o cookies.txt
```

## 安装包（macOS .dmg、Windows Setup）

推送 `v*` 标签（或手动运行 **Release** workflow）会构建 Windows 的 `FoxProfile-Setup-<version>.exe` 和 macOS (Apple Silicon) 的 `.dmg`。安装包不内置 Camoufox 浏览器：应用首次启动时会在后台下载（进度见 `logs/camoufox_fetch.log`）。用户数据（`profiles.json`、`camoufox_data/`、`logs/`、`.api_token`、`.env`）保存在 `~/Library/Application Support/FoxProfile`（macOS）或 `%APPDATA%\FoxProfile`（Windows）；设置 `FOXPROFILE_HOME` 可以更改位置。macOS 构建使用 ad-hoc 签名，未经过公证：首次打开时请右键点击，选择“打开”。

在本地构建（请使用 venv）：

```bash
pip install -r requirements.lock -r requirements-build.txt
bash packaging/build_macos.sh             # dist/FoxProfile.app + dist/FoxProfile-<version>.dmg
bash packaging/pack.sh --icon src/assets/icon.ico   # Windows: dist/FoxProfile/，然后 iscc packaging/windows/foxprofile.iss
```

## 开发

```bash
pip install -r requirements-dev.txt
ruff check src tests chrome_engine
ruff format --check src tests chrome_engine
pytest                  # 除非已下载浏览器，否则真实浏览器测试会被跳过
```

项目结构、代码规范和 PR 流程见 [CONTRIBUTING.md](CONTRIBUTING.md)（中文；欢迎用英文提交 issue 和 PR）。UI 改动遵循 [DESIGN.md](DESIGN.md)，并且需要同时修改桌面应用和 web panel。发布说明：[CHANGELOG.md](CHANGELOG.md)。

## 参与贡献

欢迎各种形式的贡献：bug 报告、功能想法、文档、翻译和代码。

- Bug 与想法：通过模板提交 [issue](https://github.com/chienbm98/foxprofile/issues/new/choose)。
- 代码：提交 pull request 前请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。
- 安全问题：**请勿**公开提交 issue，见 [SECURITY.md](SECURITY.md)。
- 所有参与者都应遵守[行为准则](CODE_OF_CONDUCT.md)。

如果 FoxProfile 对你有帮助，欢迎在 GitHub 上点个 ⭐。

## 支持

FoxProfile 免费开源，是我利用业余时间开发的，并且会一直保持下去。如果它为你节省了时间或金钱，可以请我喝杯咖啡；这些支持会用于修复 bug、跟进上游浏览器的版本更新，以及更快地回复 issue。

<a href="https://buymeacoffee.com/chienbm98"><img src="https://img.shields.io/badge/Buy%20me%20a%20coffee-%E2%98%95-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black" alt="Buy me a coffee" /></a>

## 使用须知

反检测浏览器是用于保护隐私、网站测试以及代理机构管理客户账号的正当工具。但在同一平台上运行多个账号，仍可能违反 Facebook、TikTok、Google、Shopee 等平台的条款。你需要自行对使用本软件的方式负责。

## 许可证

基于 [MIT License](LICENSE) 发布。Copyright (c) 2026 chienbm98。

## 致谢

- daijro 开发的 [Camoufox](https://github.com/daijro/camoufox) 浏览器。
- adryfish 开发的 [fingerprint-chromium](https://github.com/adryfish/fingerprint-chromium)，为 Chrome engine 所用（BSD-3）。
- [Be Vietnam Pro](https://github.com/bettergui/BeVietnamPro) 与 [JetBrains Mono](https://github.com/JetBrains/JetBrainsMono) 字体，SIL Open Font License（`src/assets/fonts/`）。
