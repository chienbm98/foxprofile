<div align="center">
  <img src="src/assets/icon.png" width="112" alt="FoxProfile 标志" />
  <h1>FoxProfile</h1>
  <p><strong>免费开源的反检测浏览器配置管理器</strong></p>
  <p>每个配置独立管理设备指纹、Cookie 和代理 · 两种引擎：Camoufox（Firefox）和 Chrome · 英文、越南语和简体中文界面 · 提供自动化 REST API 和 MCP</p>

  <p>
    <a href="https://github.com/chienbm98/foxprofile/actions/workflows/ci.yml"><img src="https://github.com/chienbm98/foxprofile/actions/workflows/ci.yml/badge.svg" alt="持续集成" /></a>
    <a href="https://github.com/chienbm98/foxprofile/releases/latest"><img src="https://img.shields.io/github/v/release/chienbm98/foxprofile" alt="最新发布版本" /></a>
    <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+" />
    <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey" alt="Windows | macOS | Linux" />
    <a href="LICENSE"><img src="https://img.shields.io/github/license/chienbm98/foxprofile" alt="MIT 许可证" /></a>
    <a href="https://buymeacoffee.com/chienbm98"><img src="https://img.shields.io/badge/Buy%20me%20a%20coffee-%E2%98%95-FFDD00?logo=buymeacoffee&logoColor=black" alt="请我喝杯咖啡" /></a>
  </p>

  <p><a href="README.md">English</a> · <a href="README.vi.md">Tiếng Việt</a> · 简体中文</p>
  <p>
    <a href="#quick-start">快速开始</a> ·
    <a href="#features">功能</a> ·
    <a href="#rest-api">REST API</a> ·
    <a href="#mcp-let-ai-agents-drive-the-browser">MCP</a> ·
    <a href="#contributing">参与贡献</a>
  </p>
</div>

![FoxProfile](docs/images/en/main.png)

FoxProfile 用于管理反检测浏览器配置：每个配置都是独立身份，拥有自己的设备指纹、Cookie、代理、时区和区域设置。默认浏览器是 [Camoufox](https://github.com/daijro/camoufox)，这是一个在浏览器引擎层伪装指纹的 Firefox 版本；此外还提供基于 [fingerprint-chromium](https://github.com/adryfish/fingerprint-chromium) 的实验性 Chrome 引擎。它可以自行托管在本机或 VPS 上，作为 GoLogin、GPM、MoreLogin 等付费反检测浏览器的替代方案。

## 目录

- [功能](#features)
- [系统要求](#requirements)
- [快速开始](#quick-start)
- [时区、区域设置与检查 IP](#timezone-locale-and-check-ip)
- [服务器模式与 Web 面板](#server-mode-and-web-panel)
- [MCP：让 AI 智能体操作浏览器](#mcp-let-ai-agents-drive-the-browser)
- [Chrome 引擎（实验性）](#chrome-engine-experimental)
- [Cookie 与指纹](#cookies-and-fingerprints)
- [配置](#configuration)
- [REST API](#rest-api)
- [开发](#development)
- [参与贡献](#contributing)
- [支持项目](#support)
- [负责任地使用](#responsible-use)
- [许可证](#license)
- [致谢](#acknowledgements)

<a id="features"></a>
## 功能

- **每个配置持久化保存指纹。** 首次启动时生成设备信息（屏幕、GPU、CPU 核心数、字体、Canvas/音频噪声）并保存；之后启动会复用同一设备。也可以按需生成新设备。
- **两种浏览器引擎。** 创建配置时可选择 Camoufox（默认，基于 Firefox）或 Chrome（基于 fingerprint-chromium，实验性）。需要时会自动下载 Chrome 构建版本。
- **持久化会话。** 历史记录、Cookie 和登录信息保存在配置目录中；下次启动时会重新打开上次打开的标签页。
- **每个配置独立代理：** 支持 HTTP/HTTPS/SOCKS4/SOCKS5，可使用或不使用认证，也支持 `host:port:user:pass` 格式，并提供代理检测器。
- **时区和区域设置**可根据出口 IP 自动设置，也可以在每个配置中固定。**检查 IP**会通过 Cloudflare、ipinfo 和 ip-api 对比出口 IP，并提示国家/时区不匹配及数据中心 IP。
- **导入/导出 Cookie：** 支持 Cookie-Editor / EditThisCookie JSON（GoLogin、GPM、Multilogin、Cookie-Editor 扩展）以及 Netscape `cookies.txt`（yt-dlp、curl、wget）。
- **导入/导出配置：** 可将配置打包为 ZIP，并选择是否包含浏览器数据，以便在不同机器间迁移。指纹始终会随配置一起导出。
- **便于快速浏览的配置表：** 每行显示引擎、模拟设备、代理（隐藏凭据）、时区/区域设置和状态。状态除了颜色外也有不同形状：带启动时间的紫色双线印记表示运行中，灰线表示正在启动，带删除线的红色印记表示启动失败。
- **筛选和搜索：** 可按运行状态、是否配置代理和 Chrome 引擎筛选（显示数量）；也可按名称或代理搜索。
- **批量操作：** 一次启动、停止或删除多个配置。
- **MCP 服务器：** AI 智能体（Claude、Cursor 等）可启动配置、浏览网页、点击、输入文字和截取屏幕。
- **服务器模式 + Web 面板：** 适用于 VPS 部署，可远程管理配置并查看浏览器画面，并由令牌保护。
- **REST API：** 提供 Swagger 文档，方便编写脚本。
- **英文（默认）、越南语和简体中文界面**可在应用内切换。字体随应用打包，无需联网下载。

<a id="requirements"></a>
## 系统要求

- Python 3.10+
- Windows、macOS 或 Linux（CI 会在三种系统上运行测试）
- 需要数百 MB 可用磁盘空间，用于 Camoufox 和 GeoIP 数据库；使用 Chrome 引擎时还需约 140-190 MB

<a id="quick-start"></a>
## 快速开始

```bash
git clone https://github.com/chienbm98/foxprofile.git
cd foxprofile

python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux/macOS

pip install -r requirements.txt
python -m camoufox fetch
```

`camoufox fetch` 会从 Camoufox 的 GitHub Releases 下载浏览器（数百 MB）。首次启动配置时还会下载 GeoIP 数据库（约 50 MB）。

启动应用：

```bash
python -m src.main
```

在 Windows 上也可以双击 `run_foxprofile.bat`。应用会打开管理器窗口，并在 `http://127.0.0.1:8000` 提供 API；API 文档位于 `http://127.0.0.1:8000/docs`。设置 `FOXPROFILE_LANG=zh` 可使用简体中文界面；设置 `FOXPROFILE_LANG=vi` 可使用越南语界面。

<a id="timezone-locale-and-check-ip"></a>
## 时区、区域设置与检查 IP

默认情况下，每次启动 Camoufox 时都会通过配置的代理查询出口 IP，并据此设置时区、区域设置、地理位置和 WebRTC IP。需要留意以下几点：

- **自动区域设置在每次启动时随机选取**，并按该 IP 所在国家/地区各语言的使用人数加权。例如，法国 IP 约有 60% 的概率使用 `fr-FR`，其他情况下可能使用 `en-FR`、`es-FR` 等。账号在不同会话间切换语言会显得可疑，因此建议为每个配置固定区域设置。
- **不同 GeoIP 数据库的结果可能不一致。** Cloudflare 可能将某个 IP 归入一个国家，而 Google 将其归入另一个国家；Camoufox 也可能选择 UTC 偏移相同但名称不同的时区（越南 IP 可能得到 `Asia/Bangkok`，而不是 `Asia/Ho_Chi_Minh`）。
- **无论浏览器外观如何，数据中心 IP 都容易触发验证码。** 对于受 Cloudflare 保护的网站，住宅或移动代理比其他设置更重要。

![创建配置对话框](docs/images/en/profile-dialog.png)

配置对话框中有 **Timezone**（时区，IANA 名称，例如 `Asia/Ho_Chi_Minh`）和 **Locale**（区域设置，例如 `vi-VN`）字段；留空表示跟随 IP。**检查 IP**会通过代理解析出口 IP，并与 Cloudflare、ipinfo 和 ip-api 的结果对比；发现国家或时区不匹配、数据中心 IP、代理的 IPv4/IPv6 出口地址不同，或区域设置仍为随机状态时，会显示提示。

<a id="server-mode-and-web-panel"></a>
## 服务器模式与 Web 面板

不显示桌面窗口，只运行 API 和 Web 面板，浏览器在隐藏模式下运行。适合部署在 VPS 上。

```bash
python -m src.server                     # http://127.0.0.1:8000
python -m src.server --host 0.0.0.0      # 对外监听时必须设置 FOXPROFILE_API_TOKEN
```

打开 `http://<host>:8000/` 进入 **Web 面板**：其中包含与桌面应用相同的配置表、筛选和批量操作；可以创建、编辑、启动和停止配置，迁移 Cookie，并**远程查看配置的屏幕画面**。即使浏览器在服务器上以隐藏模式运行，也可以点击截图并输入内容来登录或处理验证码。

| Web 面板 | 远程屏幕视图 |
| --- | --- |
| ![Web 面板](docs/images/en/panel.png) | ![远程屏幕视图](docs/images/en/panel-viewer.png) |

**安全性：** 如果监听地址不是 `127.0.0.1`，服务器在未设置 `FOXPROFILE_API_TOKEN`（至少 24 个字符）时**会拒绝启动**。Web 面板、REST API 和 MCP 共用该令牌。

```bash
# 生成随机令牌
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

在 VPS 上应将服务器置于支持 HTTPS 的反向代理（Caddy、Nginx）之后，避免令牌以明文传输。在没有显示器的 Linux 主机上，设置 `FOXPROFILE_HEADLESS=virtual`（需要 `xvfb`）可让浏览器运行在虚拟显示器上，相较于纯 headless 模式更难被检测。

完整部署指南（Ubuntu、systemd、nginx、HTTPS）：[中文指南](docs/DEPLOY.zh-CN.md)，[原越南语指南](docs/DEPLOY.md)。

<a id="mcp-let-ai-agents-drive-the-browser"></a>
## MCP：让 AI 智能体操作浏览器

FoxProfile 自带 MCP 服务器，Claude Code、Claude Desktop、Cursor、VS Code 等工具可用它管理配置并操作网页：导航、读取、点击、输入和截图。

**最快的配置方式：** 在桌面应用或 Web 面板左侧栏中点击 **Connect AI (MCP)**。该功能会为各 AI 应用生成可直接粘贴的配置，其中包含服务器地址和令牌。

![连接 AI（MCP）](docs/images/en/mcp-guide.png)

MCP 通过 FoxProfile 自身端口上的 `/mcp` 提供 HTTP 服务，因此 FoxProfile 部署在 VPS 上时也可以使用：

```bash
# Claude Code
claude mcp add --transport http foxprofile http://127.0.0.1:8000/mcp
# 带令牌的服务器：
claude mcp add --transport http foxprofile https://your-vps.example.com/mcp --header "Authorization: Bearer <token>"
```

```jsonc
// Cursor: ~/.cursor/mcp.json
{ "mcpServers": { "foxprofile": { "url": "http://127.0.0.1:8000/mcp" } } }
```

Claude Desktop 只会启动本地 MCP 服务器：可以在同一台机器上使用 `foxprofile_mcp.py`，也可以在另一台机器上通过 `npx mcp-remote` 桥接。Connect AI 对话框会同时生成这两种配置。

之后只需提出请求，例如：*“打开配置 tiktok-us-02，访问 tiktok.com，然后给我发一张截图。”*

| 分组 | 工具 |
| --- | --- |
| 配置 | `list_profiles`、`get_profile`、`create_profile`、`update_profile`、`launch_profile`、`stop_profile`、`running_profiles` |
| Cookie 与指纹 | `export_cookies`、`import_cookies`、`get_fingerprint`、`reset_fingerprint`、`check_proxy`、`check_profile_ip` |
| 页面 | `browser_navigate`、`browser_back`、`browser_snapshot`、`browser_get_text`、`browser_click`、`browser_click_at`、`browser_type`、`browser_press`、`browser_wait_for`、`browser_screenshot`、`browser_evaluate` |
| 标签页 | `browser_tabs`、`browser_tab_new`、`browser_tab_select`、`browser_tab_close` |

出于有意的设计，MCP 没有删除工具，避免智能体误删账号 Cookie。只允许打开 `http`、`https` 和 `about:blank`；`file://` 和 `about:config` 会被拦截。

<a id="chrome-engine-experimental"></a>
## Chrome 引擎（实验性）

除 Camoufox（Firefox）外，配置也可以使用 **Chrome** 引擎：这是一个通过 C++ 补丁加入指纹伪装功能的 Chromium 构建版本（[fingerprint-chromium](https://github.com/adryfish/fingerprint-chromium)，BSD-3 许可证）。创建配置时在 **Engine** 中选择；之后不能更改。浏览器构建版本（视操作系统而定，约 140-190 MB）会从 fingerprint-chromium 的 GitHub Releases 下载，并通过 SHA-256 校验。创建第一个 Chrome 配置后会在后台自动下载；如果启动时仍未下载，也会在启动过程中下载，进度会显示在日志中。也可以提前运行 `python -m chrome_engine fetch` 下载。

请选择运行 FoxProfile 的机器所用操作系统：伪装成其他操作系统会泄露本机字体信息；在 Windows/macOS 上使用 Linux 配置会被拒绝，因为 WebGL 会暴露真实 GPU。支持平台：Windows x64、macOS Apple Silicon、Linux x64（尚未测试）。详细说明和测试结果（越南语）：[chrome_engine/README.md](chrome_engine/README.md)。

<a id="cookies-and-fingerprints"></a>
## Cookie 与指纹

![Cookie 与指纹](docs/images/en/cookies.png)

点击配置行上的 Cookie 按钮，打开 **Cookies & fingerprint**。**操作前必须停止该配置的浏览器**：FoxProfile 会以 headless 模式打开配置，以读取和写入 Cookie。

- 导入的会话 Cookie 会被设置为一年有效期；否则浏览器关闭时可能会丢弃这些 Cookie。
- “New fingerprint”会删除已保存的指纹，使下次启动时使用不同的设备。更改配置的操作系统也会重新生成指纹。

<a id="configuration"></a>
## 配置

所有配置项均为可选。若要覆盖默认值，请将 `.env.example` 复制为 `.env`。

| 变量 | 默认值 | 含义 |
| --- | --- | --- |
| `FOXPROFILE_LANG` | `en` | 界面语言：`en`、`vi` 或 `zh` |
| `FOXPROFILE_PROFILES_FILE` | `profiles.json` | 配置列表文件 |
| `FOXPROFILE_DATA_DIR` | `camoufox_data` | 数据目录，每个配置各有一个子目录 |
| `FOXPROFILE_LOG_DIR` | `logs` | 日志目录 |
| `FOXPROFILE_LOG_LEVEL` | `INFO` | 日志级别 |
| `FOXPROFILE_PROXY_TIMEOUT` | `10` | 代理检测超时时间（秒） |
| `FOXPROFILE_LAUNCH_TIMEOUT` | `90` | API 等待浏览器完成启动的最长时间（秒） |
| `FOXPROFILE_HEADLESS` | `false`（服务器模式下为 `true`） | 隐藏浏览器：`true`、`false` 或 `virtual`（Linux + Xvfb） |
| `FOXPROFILE_RESTORE_TABS` | `true` | 重新打开上次运行时的标签页 |
| `FOXPROFILE_API_TOKEN` | *（空）* | API、Web 面板和 MCP 使用的令牌。API 监听地址超出 `127.0.0.1` 时必填 |
| `FOXPROFILE_API_HOST` | `127.0.0.1` | API 监听主机 |
| `FOXPROFILE_API_PORT` | `8000` | API 端口 |

### 代理格式

支持 `host:port`、`http://host:port`、`https://...`、`socks4://...`、`socks5://...`，并可选使用 `user:pass@` 认证。也支持代理服务商提供的 `host:port:user:pass` 格式。留空表示直接连接。

### 数据目录结构

```text
profiles.json                                  配置列表（名称、引擎、代理、操作系统、时区、区域设置）
camoufox_data/<profile>/                       浏览器数据：Cookie、历史记录、localStorage
camoufox_data/<profile>/fingerprint.json       设备指纹（Camoufox 引擎）
camoufox_data/<profile>/chrome_persona.json    设备指纹（Chrome 引擎）
camoufox_data/<profile>/tabs.json              下次启动时重新打开的标签页
logs/foxprofile_YYYYMMDD.log                   每日日志
```

> [!WARNING]
> `camoufox_data/` 保存着每个账号的登录 Cookie。切勿提交或分享此目录。

<a id="rest-api"></a>
## REST API

API 前缀为 `/api/v1`。应用运行时，可在 `/docs` 查看完整参考文档。
Web 面板会通过 `Accept-Language` 发送当前界面语言。常见 API 错误和字段校验信息已提供简体中文翻译；尚未映射的消息会保留原文。其他客户端可使用 `zh` 或 `zh-CN` 请求中文消息。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 健康检查 |
| `GET` / `POST` | `/profiles` | 列出 / 创建配置 |
| `GET` / `PATCH` / `DELETE` | `/profiles/{name}` | 读取 / 更新 / 删除配置（`engine` 不可更改） |
| `GET` | `/profiles/{name}/data-dir` | 获取配置数据目录的路径 |
| `POST` | `/profiles/{name}/export` | 将配置导出为 ZIP |
| `POST` | `/profiles/import` | 从 ZIP 导入配置 |
| `GET` | `/profiles/{name}/cookies?format=json\|netscape` | 导出 Cookie |
| `POST` | `/profiles/{name}/cookies` | 导入 Cookie（`{"content": "<JSON or cookies.txt>"}`） |
| `GET` / `DELETE` | `/profiles/{name}/fingerprint` | 查看 / 生成新指纹 |
| `GET` | `/profiles/{name}/ip-check` | 查看 Cloudflare/ipinfo/ip-api 对配置出口 IP 的定位结果及不匹配提示 |
| `GET` | `/browser` | 正在运行的配置 |
| `GET` | `/browser/{name}/status` | 查看配置是否正在运行 |
| `POST` | `/browser/{name}/launch` | 启动并等待就绪或失败（已运行或忙碌时返回 409） |
| `POST` | `/browser/{name}/stop` | 停止配置 |
| `POST` | `/proxy/check` | 检查代理 |
| `POST` | `/proxy/geo-check` | 对尚未保存的 `{proxy, timezone, locale}` 执行与 `ip-check` 相同的检查 |
| `POST` | `/browser/{name}/page/navigate` · `back` | 在当前标签页打开 URL、返回上一页 |
| `GET` | `/browser/{name}/page/snapshot` · `text` | 页面的无障碍树（用于选择器定位）、页面文本 |
| `POST` | `/browser/{name}/page/click` · `type` · `press` · `wait` | 点击、输入、按键、等待元素（使用 Playwright 选择器） |
| `POST` | `/browser/{name}/page/click-at` · `keyboard` | 点击指定坐标、向当前焦点元素输入文字 |
| `GET` | `/browser/{name}/page/screenshot` | 当前标签页的 PNG（使用 `?format=json` 获取 base64） |
| `POST` | `/browser/{name}/page/evaluate` | 执行 JavaScript |
| `GET` / `POST` | `/browser/{name}/page/tabs` | 列出标签页 / 打开新标签页 |
| `POST` / `DELETE` | `/browser/{name}/page/tabs/{index}/select` · `/page/tabs/{index}` | 选择 / 关闭标签页 |
| `GET` | `/mcp/setup?base_url=...` | 获取各 AI 应用的 MCP 配置（由 Connect AI 对话框使用） |

设置 `FOXPROFILE_API_TOKEN` 后，除 `/health` 和 `/info` 外，每个请求都需要携带 `Authorization: Bearer <token>`。

示例：

```bash
# 创建一个使用代理的 macOS 配置。若要使用 Chrome 引擎，添加 "engine": "chrome"（默认值为 "camoufox"）。
curl -X POST http://127.0.0.1:8000/api/v1/profiles \
  -H "Content-Type: application/json" \
  -d '{"name": "tiktok-us-02", "os_type": "macos", "proxy": "socks5://user:pass@203.0.113.10:1080"}'

# 启动。运行成功后返回 200，失败时返回 502 和原因。
# 添加 ?wait=false 可立即返回（202）。
curl -X POST http://127.0.0.1:8000/api/v1/browser/tiktok-us-02/launch

# 将 Cookie 导出为 cookies.txt
curl "http://127.0.0.1:8000/api/v1/profiles/tiktok-us-02/cookies?format=netscape" -o cookies.txt
```

<a id="development"></a>
## 开发

```bash
pip install -r requirements-dev.txt
ruff check src tests chrome_engine
ruff format --check src tests chrome_engine
pytest                  # 获取浏览器后才会运行真实浏览器测试；否则会跳过
```

项目目录结构、代码规范和 PR 流程见 [CONTRIBUTING.md](CONTRIBUTING.md)（越南语；欢迎使用英文提交 issue 和 PR）。UI 改动应遵循 [DESIGN.md](DESIGN.md)，并同时覆盖桌面应用和 Web 面板。版本说明见 [CHANGELOG.md](CHANGELOG.md)。

<a id="contributing"></a>
## 参与贡献

欢迎通过各种方式参与：报告问题、提出功能想法、改进文档、翻译或提交代码。

- 报告问题或提出想法：使用模板创建 [issue](https://github.com/chienbm98/foxprofile/issues/new/choose)。
- 提交代码：创建 pull request 前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。
- 安全问题：**请勿**公开创建 issue，请参阅 [SECURITY.md](SECURITY.md)。
- 所有参与者都应遵守[行为准则](CODE_OF_CONDUCT.md)。

如果 FoxProfile 对你有帮助，欢迎在 GitHub 上点亮 ⭐。

<a id="support"></a>
## 支持项目

FoxProfile 是免费开源软件，由我利用业余时间开发，并将持续保持免费。如果它为你节省了时间或金钱，可以请我喝杯咖啡；这些支持将用于修复问题、跟进上游浏览器版本并更快回复 issue。

<a href="https://buymeacoffee.com/chienbm98"><img src="https://img.shields.io/badge/Buy%20me%20a%20coffee-%E2%98%95-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black" alt="请我喝杯咖啡" /></a>

<a id="responsible-use"></a>
## 负责任地使用

反检测浏览器可用于保护隐私、网页测试以及代理机构管理客户账号，都是正当用途。在同一平台上运行多个账号仍可能违反 Facebook、TikTok、Google、Shopee 等平台的服务条款。你需要对本软件的使用方式负责。

<a id="license"></a>
## 许可证

本项目基于 [MIT License](LICENSE) 发布。版权所有 (c) 2026 chienbm98。

<a id="acknowledgements"></a>
## 致谢

- 感谢 daijro 开发的 [Camoufox](https://github.com/daijro/camoufox) 浏览器。
- 感谢 adryfish 提供 Chrome 引擎所用的 [fingerprint-chromium](https://github.com/adryfish/fingerprint-chromium)（BSD-3）。
- 感谢 [Be Vietnam Pro](https://github.com/bettergui/BeVietnamPro) 和 [JetBrains Mono](https://github.com/JetBrains/JetBrainsMono) 字体，采用 SIL Open Font License（位于 `src/assets/fonts/`）。
