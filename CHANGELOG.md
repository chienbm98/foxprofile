# 更新日志

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)；版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [2.6.2] - 2026-10-17

### 变更
- 安装包变小：内置浏览器只保留本机系统会用到的字体（profile 只能伪装成本机系统，其他系统的字体用不到），macOS dmg 改用 LZMA 压缩。可见字体和指纹不变。

## [2.6.1] - 2026-10-16

### 变更
- 文档改为简体中文：`README.vi.md` 改为 `README.zh-CN.md`，`CONTRIBUTING.md`、`SECURITY.md`、`CODE_OF_CONDUCT.md`、`docs/DEPLOY.md`、`DESIGN.md`、`CHANGELOG.md` 和 issue/PR 模板同样改为中文。

### 移除
- 越南语界面。界面语言现在只有 English 和简体中文；之前保存的越南语选项（`settings.json` 中的 `vi`，或 `FOXPROFILE_LANG=vi`）会被忽略，改为跟随系统语言，系统语言不受支持时使用 English。

## [2.6.0] - 2026-10-16

### 新增
- 安装包内置 FoxProfile 自己的 Camoufox 构建（156.0.1-beta.36-fp1，`patches/foxprofile-session-key.patch`），首次运行不再下载原版。安装包约 1.4GB。
- 每个 profile 拥有独立的 canvas/WebGL 噪声密钥（`fingerprint.json` 中的 `noise_key`）：多次打开之间噪声保持不变，同时在不同网站之间、不同 profile 之间仍各不相同。重新生成 fingerprint 会更换密钥。

## [2.5.0] - 2026-10-16

### 新增
- Chrome engine 支持按条目设置 fingerprint（桌面应用的 Fingerprint 选项卡、web panel、REST、MCP），每种 engine 只显示浏览器真正能做到的模式。已支持：CPU 核数（masked/custom/real）、WebGL GPU（masked/real）、audio（noise/real）、WebRTC（masked/off/real）、timezone、语言、位置及位置权限、拦截内网端口扫描（masked/real）。Chrome 的 canvas 始终为 real：这个 fingerprint-chromium 构建的 canvas 噪声会让 `measureText()` 返回约 0（fingerprint-chromium#96）。Chrome 做不到的条目（user agent、独立的 WebGL 噪声、屏幕、字体、媒体设备、语音）仍会显示，但标注为 "Not supported by the Chrome engine"。`GET /fingerprint/options` 和 MCP `fingerprint_options` 接受 `engine` 参数。
- 从未调整过设置的旧 Chrome profile 会迁移到 Chrome 的默认值（语言跟随出口 IP，位置权限为 "prompt"），行为保持不变。
- 不使用 proxy 时，位置处于 masked 模式的 Chrome profile 每次打开都会查询一次你本机的 IP（与 Camoufox 使用 geoip 时相同），除非位置权限为 "block"。

## [2.4.0] - 2026-10-15

### 新增
- 桌面应用和 web panel 新增简体中文界面（简体中文）；默认跟随系统语言，所选语言会被保存。
- fingerprint 的 "Language" 项改为从列表中选择（English / 简体中文），不再手动输入。

### 修复
- 桌面应用：使用 English 界面时，"Launch" 按钮不再被折成两行。
- 密码中含有 `@` 或 `:` 的 `host:port:user:pass` 格式 proxy 不再被忽略（此前 profile 会不经过 proxy 直接打开）。接受 `[2001:db8::1]` 形式的 IPv6 proxy；proxy 主机名最长 253 个字符。
- Profile 名称不再区分大小写：在 Windows/macOS 上，"Demo" 和 "demo" 不能再创建出共用同一数据目录的两个 profile。仅大小写不同的重命名仍会保留数据；含控制字符的名称会被拒绝。
- 重命名为一个遗留有数据目录的名称时，现在返回 409 错误，而不是弄坏 profile 列表。`profiles.json` 采用原子写入，并发操作（API、MCP、应用）不再互相覆盖，也不再导致 500 错误或误删刚重新创建的 profile 的目录。
- 无法联网的 proxy 现在给出易懂的错误（"no internet connection through proxy host:port"），而不是内部错误字符串；细节仍记录在日志中。
- MCP `update_profile(proxy="")` 现在可以清除 proxy。
- 页面控制现在会拒绝经过百分号编码的 scheme（`%66ile:`）以及 `[::1` 这类损坏的 URL。
- Web panel："New fingerprint" 的确认不再直接关闭 cookie 对话框；Esc 会关闭实时画面查看器以及最上层的对话框；无法连接 server 时显示错误和重试按钮，而不是空白页；运行时保存按钮和 cookie 操作会被锁定；422 错误以易读形式显示。
- 桌面应用：生成新 fingerprint 前会先确认；表头的复选框不再取消其他页面上已选中的 profile；侧边栏显示 profile 数量和正在运行的浏览器数量；删除对话框明确说明 cookie 和数据将被永久删除。

### 变更
- 所有 profile 都固定为当前运行机器的操作系统：选择其他系统会暴露本机的字体和渲染方式。API 会拒绝不同的 `os_type`，MCP 不再有 `os_type` 参数。
- 新 profile 的默认 engine 是 Camoufox (Firefox)。每个 Camoufox profile 有 18 项 fingerprint 设置（`profiles.json` 中的 `fingerprint`；REST `PUT /profiles/{name}/fingerprint/settings`、`GET /fingerprint/options`、`POST /profiles/{name}/fingerprint/regenerate`；MCP `update_fingerprint_settings`、`fingerprint_options`）。设备从真实设备库中选取一次，然后冻结在 `fingerprint.json`（v2）中；v1 文件会在下次打开时重新生成。
- 桌面应用和 web panel 的默认界面语言是 English；设置 `FOXPROFILE_LANG=vi`（或在应用中点击 "Tiếng Việt"）可使用越南语。

## [2.3.1] - 2026-10-09

### 修复
- Web panel：浏览器窗口宽度小于约 1460px 时，profile 表格不再把操作列（Launch/Stop）挤出去；表格现在会根据自身的实际宽度调整布局。
- 当 profile 同时通过 API 或 MCP 被打开时，桌面应用中它不再卡在 "Launching" 状态；对同一个 profile 同时发出两个打开命令，也不会再启动两个浏览器。

## [2.3.0] - 2026-10-09

### 变更
- 桌面应用和 web panel 的界面按统一的设计体系重新设计（见 `DESIGN.md`）：浅色纸张底色、绿色侧边栏、列对齐的 profile 表格（含 Device / Proxy / Timezone · Locale 列），以及用形状和颜色共同区分的状态“印章”（运行中、启动中、失败）。Be Vietnam Pro 和 JetBrains Mono 字体已内置（OFL），无需联网即可使用。
- 两种界面都新增带数量的 profile 筛选（全部、运行中、有/无 proxy、Chrome engine）；web panel 另外新增批量操作和独立的确认对话框；桌面应用运行时即可在越南语 / English 之间切换。
- 越南语界面中的专业术语保留英文（fingerprint、engine、timezone、locale）。

### 新增
- 在 Camoufox 之外新增 **Chrome（实验性）** 内核，基于 fingerprint-chromium：创建 profile 时可在应用、web panel、REST API（`"engine": "chrome"`）和 MCP（`create_profile(engine="chrome")`）中选择。内核创建后不可更改。Cookie、fingerprint、页面控制、重新打开标签页和 Check IP 的用法与 Camoufox profile 相同。浏览器构建会在创建第一个 Chrome profile 时于后台自动下载，如果缺失则在打开 profile 时下载（也可以用 `python -m chrome_engine fetch` 手动下载）。
- 所有填写 proxy 的地方都接受 `host:port:user:pass` 格式（proxy 服务商常见的格式），包括带 `socks5://` 前缀的写法。
- 停止 profile 时记住已打开的标签页并在下次重新打开（标签页变化时每 2 秒保存一次到 `camoufox_data/<profile>/tabs.json`，仅限 `http`/`https`，最多 30 个标签页）。可用 `FOXPROFILE_RESTORE_TABS=false` 关闭。

### 修复
- 使用 `socks5://`/`socks4://` proxy 时的 DNS 泄露：打开 profile 时的出口 IP 查询以及 **Check IP** 按钮此前会用本机 DNS 解析域名（暴露真实运营商）。现在改用 `socks5h://`/`socks4a://`，由 proxy 负责解析。浏览器本身不受影响。
- `HEADLESS=virtual` 模式（Linux server）在 profile 打开失败（例如 proxy 无法连接）或 runner 被强制终止/崩溃时，不再遗漏 Xvfb 进程。Runner 自行管理虚拟显示器，并记录它启动的 Xvfb（按 PID 和启动时间，保存在用户专属的临时目录），以便 launcher 或下一次启动关闭正确的那个 Xvfb。

## [2.2.0] - 2026-10-08

### 新增
- 可为每个 profile 固定 timezone（IANA）和语言（`vi-VN`）；留空时仍自动跟随 IP。
- **Check IP** 按钮：把出口 IP 与 Cloudflare、ipinfo 和 ip-api 对比，对国家/timezone 不一致、机房 IP、双栈 proxy 和随机语言给出警告。应用、web panel、REST API（`GET /profiles/{name}/ip-check`、`POST /proxy/geo-check`）和 MCP（`check_profile_ip`）都提供。
- Linux server 部署指南（`docs/DEPLOY.md`、`deploy/`）以及手动 e2e 脚本（`tests/e2e/`）。

## [2.1.0] - 2026-10-08

### 新增
- 面向 AI agent 的 MCP server（27 个工具），支持 stdio 以及 `/mcp` 路径的 HTTP。
- 受 token 保护的 web panel，可远程查看和控制浏览器画面。
- 隐藏浏览器的 server 模式（`python -m src.server`）。
- 面向 Claude Code、Cursor、VS Code 和 Claude Desktop 的 MCP 连接指南对话框。

### 修复
- Server 模式现在能正确读取 `.env` 中的 `FOXPROFILE_HEADLESS`。

## [2.0.0] - 2026-10-08

FoxProfile 首次发布：按 profile 固定的 fingerprint、独立 proxy、cookie 导出/导入（JSON 和 Netscape）、REST API、越南语/英语界面。

[Unreleased]: https://github.com/chienbm98/foxprofile/compare/v2.3.1...HEAD
[2.3.1]: https://github.com/chienbm98/foxprofile/compare/v2.3.0...v2.3.1
[2.3.0]: https://github.com/chienbm98/foxprofile/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/chienbm98/foxprofile/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/chienbm98/foxprofile/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/chienbm98/foxprofile/releases/tag/v2.0.0
