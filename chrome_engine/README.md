# Chrome engine（实验性）

FoxProfile 的第二个浏览器 engine，与 Camoufox 并行运行：一个已打好补丁的 Chromium 构建，在 C++ 层直接伪装 fingerprint（[fingerprint-chromium](https://github.com/adryfish/fingerprint-chromium)，BSD-3，基于 ungoogled-chromium）。本 engine 不自行编译 Chromium，而是下载一个固定了 checksum 的现成构建，再补上 fork 里缺少的部分。

Engine 已接入 FoxProfile：profile 有 `engine` 字段（`camoufox` 或 `chrome`，创建后不可更改）。`BrowserLauncher` 会为 Chrome profile 运行 `python -m chrome_engine.runner`（与 Camoufox runner 使用相同的 protocol），cookie 通过 `cookie_tool.py` 配合 `chrome` engine 处理，Chrome profile 的 fingerprint 保存在 `chrome_persona.json`。

## 安装与使用

```bash
python -m chrome_engine fetch            # 下载约 190 MB，校验 SHA-256，解压到缓存目录
python -m chrome_engine info             # 已安装的路径
python -m chrome_engine probe data/alice --timezone Asia/Ho_Chi_Minh --locale vi-VN
python -m chrome_engine open  data/alice --proxy "socks5://user:pass@host:1080" --url https://example.com
```

默认缓存目录是 `%LOCALAPPDATA%\foxprofile\chrome`、`~/Library/Caches/foxprofile/chrome` 或 `~/.cache/foxprofile/chrome`。设置 `FOXPROFILE_CHROME_HOME` 可以更改。

```python
from chrome_engine import ChromeEngine

async with ChromeEngine("data/alice", proxy="http://u:p@1.2.3.4:8080") as context:
    page = context.pages[0]
    await page.goto("https://example.com")
```

`context` 就是普通的 Playwright `BrowserContext`。供 FoxProfile 使用的 runner：

```bash
python -m chrome_engine.runner <name> <proxy|None> <windows|macos|linux> [timezone] [locale]
# 输出 CONTROL:<port>:<token>、BROWSER_STARTED、BROWSER_CLOSED / LAUNCH_FAILED: ...
```

## Engine 给 fork 补上了什么

| fork / Playwright 的问题 | Engine 的处理方式 | 文件 |
|---|---|---|
| 150.0.7871.186 版在 canvas 上绘制 emoji 时 renderer 会崩溃（实测约 50% 的启动会出现） | 固定使用 148.0.7778.215 版（16/16 次没有崩溃），并带有回归测试 | `release.py` |
| 没有按 profile 固定的身份 | Persona（seed、OS、OS 版本、brand、核数、timezone、locale）保存在 `chrome_persona.json` | `persona.py` |
| `--proxy-server` 不接受密码，不支持带认证的 SOCKS5 | 在 loopback 上建立 proxy bridge，转发到带认证的上游 HTTP/HTTPS/SOCKS5；域名交给 proxy 解析，不在本机解析（不泄露 DNS） | `proxy_bridge.py` |
| Timezone/locale 不跟随 proxy 的 IP | 通过 bridge 查询出口 IP，使用 Camoufox 的 GeoIP；查询失败时**拒绝启动**（而不是暴露本机真实的 timezone） | `geo.py`, `engine.py` |
| Playwright 会添加网页能检测到的开关（`--enable-automation`、`--disable-popup-blocking`、`--hide-scrollbars`、`--force-color-profile=srgb`、关闭 bfcache、关闭 throttling、`--no-sandbox`、关闭 storage partitioning 等） | 有选择地移除，包括从当前安装的 Playwright driver 读取到的 `--disable-features` 字符串 | `engine.py` |
| Headless 报告屏幕为 800x600，scrollbar 为 0px | `--screen-info`/`--window-size` 设为 1920x1080，保留 scrollbar | `engine.py` |
| WebRTC：fork 屏蔽了所有 UDP；重新开启则会泄露局域网 IP（fork 没有用 mDNS 遮蔽） | 有 proxy：屏蔽 UDP。无 proxy：只暴露公网 IP（`default_public_interface_only`），绝不暴露局域网 IP | `engine.py` |
| Persona 的 OS 与宿主机不同时自相矛盾 | 兼容性表；Windows 或 macOS 宿主机上的 Linux persona 会被拒绝（WebGL 仍会报告本机真实的 GPU） | `persona.py` |
| 需要知道网页实际看到了什么 | Probe 从 window、worker、iframe、ServiceWorker、SharedWorker、HTTP header 读取；`check()` 列出所有不一致之处 | `probe.py` |

## Fingerprint 设置（Fingerprint 选项卡）

Runner 读取 profile 的 `fingerprint`（`fpsettings.saved(..., "chrome")`），`settings.py` 将其转换为开关、preferences 和 Playwright 操作。这些设置始终优先于传入的 `timezone`/`locale` 和 `chrome_persona.json`；它们只在内存中生效，不会写入 persona。Preferences（WebRTC、位置权限、Local Network Access）在每次启动时重新写入。已在 148.0.7778.215、macOS 上用 probe 验证：

| 条目 | 模式 | 实现方式 |
|---|---|---|
| hardware_concurrency | mask / custom / real | `--fingerprint-hardware-concurrency`（real = 本机核数） |
| webgl_meta | mask / real | real = `--disable-spoofing=gpu`（本机 GPU；mask = 按 seed 生成的 GPU） |
| canvas | real（固定） | 始终 `--disable-spoofing=canvas`：canvas 噪声会让 `measureText()` 返回约 0（fingerprint-chromium#96，148 和 150 都有）。同时也会关闭 WebGL 读取像素的噪声，因此没有单独的 `webgl_noise` |
| audio | noise / real | `--disable-spoofing=audio` |
| webrtc | mask / off / real | mask：按 proxy 设置 pref policy；off：`disable_non_proxied_udp`；real：`--webrtc-ip-handling-policy=default`（暴露局域网 IP）。off 模式下 `RTCPeerConnection` API 仍然存在 |
| timezone, language | mask / custom / real | `--timezone`、`--lang`/`--accept-lang`；mask 跟随出口 IP（需要 proxy），real 让浏览器按本机自行获取 |
| geo_permission | prompt / allow / block | block：pref `geolocation=2`；allow：`grant_permissions`；prompt：pref `3` |
| geolocation | mask / custom / real | `context.set_geolocation`；real 不伪造位置 |
| port_scan | mask / real | mask：pref `local_network_access`/`loopback_network` = block；real：`--disable-features=LocalNetworkAccessChecks`。同时拦截 `fetch` 和 `ws://localhost`，包括局域网 IP；没有例外名单 |
| os, platform | 固定 | 始终是本机的 OS |
| user_agent, webgl_noise, screen, fonts, media_devices, voices | 不支持 | UA 必须与 client hints 一致；`--fingerprint-screen-*` 在此版本中无效，`--screen-info` 只在 headless 下可用；字体/设备由本机提供 |

## Persona 与宿主机的兼容性

| 宿主机 \ Persona | Windows | macOS | Linux |
|---|---|---|---|
| Windows | ok | 警告：Windows 字体会通过字体测量泄露 | **拒绝**：WebGL 会报告 Direct3D 11 |
| Linux | 警告：Linux 字体 | 警告：Linux 字体 | ok |
| macOS | 警告：macOS 字体，overlay scrollbar 为 0px | ok | **拒绝**：WebGL 会报告真实的 Apple GPU |

Windows 和 macOS 两行是直接实测得到的；Linux 一行是推断，尚未验证。

该 fork 的 macOS 版本只有 arm64：不支持 Intel Mac（`fetch` 会报错，而不是下载一个无法运行的版本）。在 Apple Silicon Mac 上通过 Rosetta 运行的 x86_64 Python 仍会被识别为 arm64。

## 测试结果（2026-10-09，Windows 11，fingerprint-chromium 148.0.7778.215）

```bash
pytest chrome_engine/tests                 # 191 个测试；需要 browser 的测试在尚未 fetch 时自动跳过
pytest chrome_engine/tests -m "not browser"
python chrome_engine/e2e/detection_e2e.py headed headless   # 需要联网
```

- 单元测试：release、fetch（checksum、回滚、path traversal）、persona、proxy bridge（带认证的 HTTP/SOCKS5、密码错误、上游挂掉、25 个并行 tunnel、3 MB body）、probe check（每一种不一致都会被捕获）。
- 使用真实 browser 的集成测试：headed/headless/offscreen 下 fingerprint 一致、brand 为 Chrome/Edge、Windows 上的 macOS persona、canvas emoji 不崩溃、相同 seed = 相同设备、不同 seed = 不同设备、cookie/localStorage/persona 在后续启动中保留、带认证的 HTTP 和 SOCKS5 proxy（不泄露 DNS）、proxy 密码错误时绝不直连、geoip、弹窗拦截正常工作、storage partitioning 已开启、`Runtime.enable` 不暴露、WebRTC 跟随 proxy、3 个并行 profile 互相隔离。
- Runner：`CONTROL` → `BROWSER_STARTED` 的顺序正确，通过 control server 控制，标签页保存/恢复，runner 被强制终止后仍能重新打开 profile，关闭最后一个标签页 → `BROWSER_CLOSED`。
- 公开检测页面，headed 和 headless 都测试：sannysoft 全部通过，通过 Cloudflare challenge，BrowserScan 为 "Normal"，CreepJS 的 headless 比例为 0%（在 Playwright 下运行的真实 Chrome：33% headless）。

## 测试结果（2026-10-09，macOS 15.3，Apple M1 Pro，fingerprint-chromium 148.0.7778.215）

- `fetch`：下载 `.dmg`，校验 SHA-256，用 `hdiutil` 解压；ad-hoc 签名的 arm64 二进制文件可以运行。
- 使用真实 browser 的集成测试：23 个通过，1 个跳过（`test_macos_persona_on_windows_host`，只在 Windows 上运行）。
- macOS persona 的 probe（headed 和 headless）：0 个问题；WebGL 报告的是伪造的 GPU（例如 Apple M4），不会暴露真实芯片。
- Windows persona 的 probe：scrollbar 为 0px（macOS 在“自动”设置下的 overlay scrollbar）；macOS 字体被暴露。
- Linux persona 的 probe：WebGL 暴露 `ANGLE Metal Renderer: Apple M1 Pro`，因此这种组合会被拒绝。
- 公开检测页面（headed 和 headless，macOS persona）：sannysoft 全部通过，通过 Cloudflare challenge，BrowserScan 为 "Normal"，CreepJS 的 headless 比例为 0%。

## 已知限制

- 字体是宿主机的字体。与宿主机 OS 不同的 persona 会通过字体测量暴露。
- WebGL 渲染出的图像（像素）仍来自真实 GPU；只有 vendor/renderer 字符串和参数被伪造。
- WebRTC 没有像真实 Chrome 那样的 mDNS 形式 host candidate（fork 关闭了它）。不会泄露 IP，但这是一个细微的差异。
- `userAgentData.fullVersionList` 报告的是 fork 选定的补丁版本（例如 148.0.7778.97），而不是真实的 build 号。
- 尚未在 Linux 上验证；`.dmg` 版本只能在 macOS 上解压，并且只能在 Apple Silicon 上运行。
- macOS persona 始终报告 `devicePixelRatio` 为 1，而真实的 MacBook 几乎总是 2（Retina）。在 headless 下，`availHeight` 等于 `height`（没有扣除菜单栏）。
- macOS 上的 Windows persona：scrollbar 为 0px。设置 `defaults write org.chromium.Chromium AppleShowScrollBars Always` 可以恢复到 15px（真实 Windows 为 17px），但该设置会作用于本机所有使用相同 bundle id 的 Chromium。
- 尚未处理通过 CDP 响应时间进行的检测。
- Proxy bridge 在 `127.0.0.1` 的随机端口上监听，没有密码（Chromium 无法发送密码）。网页无法使用它（无法发送 `CONNECT`，普通请求会返回 400），但同一台机器上的其他进程可以在 profile 打开期间通过该 profile 的 proxy 访问外网。
- 依赖外部 fork：升级版本前必须重新运行全部测试（尤其是 `test_emoji_canvas_does_not_crash`），然后再更改 `DEFAULT_VERSION`。
