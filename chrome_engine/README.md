# Chrome engine (thử nghiệm)

Engine trình duyệt thứ hai cho FoxProfile, chạy song song với Camoufox: một bản Chromium đã vá sẵn để giả fingerprint ngay trong C++ ([fingerprint-chromium](https://github.com/adryfish/fingerprint-chromium), BSD-3, dựa trên ungoogled-chromium). Engine không tự build Chromium. Nó tải một bản build đã ghim checksum rồi thêm những phần mà fork chưa có.

Engine đã được nối vào FoxProfile: profile có trường `engine` (`camoufox` hoặc `chrome`, cố định sau khi tạo). `BrowserLauncher` chạy `python -m chrome_engine.runner` cho profile Chrome (cùng protocol với runner Camoufox), cookie đi qua `cookie_tool.py` với engine `chrome`, và vân tay của profile Chrome là `chrome_persona.json`.

## Cài và dùng

```bash
python -m chrome_engine fetch            # tải ~190 MB, kiểm SHA-256, giải nén vào cache
python -m chrome_engine info             # đường dẫn đã cài
python -m chrome_engine probe data/alice --timezone Asia/Ho_Chi_Minh --locale vi-VN
python -m chrome_engine open  data/alice --proxy "socks5://user:pass@host:1080" --url https://example.com
```

Thư mục cache mặc định là `%LOCALAPPDATA%\foxprofile\chrome`, `~/Library/Caches/foxprofile/chrome` hoặc `~/.cache/foxprofile/chrome`. Đặt `FOXPROFILE_CHROME_HOME` để đổi.

```python
from chrome_engine import ChromeEngine

async with ChromeEngine("data/alice", proxy="http://u:p@1.2.3.4:8080") as context:
    page = context.pages[0]
    await page.goto("https://example.com")
```

`context` là một `BrowserContext` Playwright bình thường. Runner cho FoxProfile:

```bash
python -m chrome_engine.runner <tên> <proxy|None> <windows|macos|linux> [timezone] [locale]
# in ra CONTROL:<port>:<token>, BROWSER_STARTED, BROWSER_CLOSED / LAUNCH_FAILED: ...
```

## Engine thêm gì vào fork

| Vấn đề của fork / Playwright | Cách engine xử lý | File |
|---|---|---|
| Bản 150.0.7871.186 crash renderer khi vẽ emoji lên canvas (đo được ~50% số lần mở) | Ghim bản 148.0.7778.215 (16/16 lần không crash), có test hồi quy | `release.py` |
| Không có danh tính cố định theo profile | Persona (seed, OS, phiên bản OS, brand, số nhân, timezone, locale) lưu `chrome_persona.json` | `persona.py` |
| `--proxy-server` không nhận mật khẩu, không hỗ trợ SOCKS5 có auth | Proxy bridge trên loopback, chuyển qua upstream HTTP/HTTPS/SOCKS5 có auth; tên miền gửi cho proxy, không phân giải tại máy (không rò DNS) | `proxy_bridge.py` |
| Timezone/locale không theo IP proxy | Tra IP thoát qua bridge, dùng GeoIP của Camoufox; tra thất bại thì **từ chối mở** (thay vì lộ timezone máy thật) | `geo.py`, `engine.py` |
| Playwright thêm các switch mà trang web đo được (`--enable-automation`, `--disable-popup-blocking`, `--hide-scrollbars`, `--force-color-profile=srgb`, tắt bfcache, tắt throttling, `--no-sandbox`, tắt storage partitioning…) | Bỏ chọn lọc, gồm cả đúng chuỗi `--disable-features` đọc từ driver Playwright đang cài | `engine.py` |
| Headless báo màn hình 800x600, scrollbar 0px | `--screen-info`/`--window-size` 1920x1080, giữ scrollbar | `engine.py` |
| WebRTC: fork chặn hết UDP; nếu mở lại thì lộ IP LAN (fork không che bằng mDNS) | Có proxy: chặn UDP. Không proxy: chỉ lộ IP public (`default_public_interface_only`), không bao giờ lộ IP LAN | `engine.py` |
| Persona OS khác host tự mâu thuẫn | Bảng tương thích; persona Linux trên host Windows hoặc macOS bị từ chối (WebGL vẫn báo GPU thật của máy) | `persona.py` |
| Cần biết trang web thực sự thấy gì | Probe đọc từ window, worker, iframe, ServiceWorker, SharedWorker, header HTTP; `check()` liệt kê mọi chỗ lệch | `probe.py` |

## Tương thích persona ↔ máy chủ

| Máy chủ \ Persona | Windows | macOS | Linux |
|---|---|---|---|
| Windows | ok | cảnh báo: font Windows lộ qua đo font | **từ chối**: WebGL báo Direct3D 11 |
| Linux | cảnh báo: font Linux | cảnh báo: font Linux | ok |
| macOS | cảnh báo: font macOS, scrollbar overlay 0px | ok | **từ chối**: WebGL báo GPU Apple thật |

Hàng Windows và macOS được đo trực tiếp; hàng Linux là suy luận và chưa kiểm chứng.

Bản macOS của fork chỉ có arm64: Mac Intel không được hỗ trợ (`fetch` báo lỗi thay vì tải về một bản không chạy được). Python x86_64 chạy qua Rosetta trên Mac Apple Silicon vẫn được nhận là arm64.

## Kết quả kiểm thử (2026-10-09, Windows 11, fingerprint-chromium 148.0.7778.215)

```bash
pytest chrome_engine/tests                 # 191 test; test cần browser tự skip nếu chưa fetch
pytest chrome_engine/tests -m "not browser"
python chrome_engine/e2e/detection_e2e.py headed headless   # cần internet
```

- Test đơn vị: release, fetch (checksum, rollback, path traversal), persona, proxy bridge (HTTP/SOCKS5 có auth, sai mật khẩu, upstream chết, 25 tunnel song song, body 3 MB), probe check (mỗi loại lệch đều bị bắt).
- Test tích hợp với browser thật: fingerprint nhất quán ở headed/headless/offscreen, brand Chrome/Edge, persona macOS trên Windows, emoji canvas không crash, cùng seed = cùng thiết bị, khác seed = khác thiết bị, cookie/localStorage/persona giữ qua lần mở sau, proxy HTTP và SOCKS5 có auth (không rò DNS), sai mật khẩu proxy không bao giờ đi thẳng, geoip, popup blocker hoạt động, storage partitioning bật, `Runtime.enable` không lộ, WebRTC theo proxy, 3 profile song song cách ly nhau.
- Runner: đúng thứ tự `CONTROL` → `BROWSER_STARTED`, điều khiển qua control server, lưu/khôi phục tab, runner bị kill cứng vẫn mở lại được profile, đóng tab cuối → `BROWSER_CLOSED`.
- Trang kiểm tra công khai, cả headed và headless: sannysoft pass toàn bộ, vượt Cloudflare challenge, BrowserScan "Normal", CreepJS 0% headless (Chrome thật chạy dưới Playwright: 33% headless).

## Kết quả kiểm thử (2026-10-09, macOS 15.3, Apple M1 Pro, fingerprint-chromium 148.0.7778.215)

- `fetch`: tải `.dmg`, kiểm SHA-256, giải nén bằng `hdiutil`; binary arm64 ký ad-hoc chạy được.
- Test tích hợp với browser thật: 23 pass, 1 skip (`test_macos_persona_on_windows_host`, chỉ chạy trên Windows).
- Probe persona macOS (headed và headless): 0 issue; WebGL báo GPU đã giả (vd. Apple M4), không lộ chip thật.
- Probe persona Windows: scrollbar 0px (scrollbar overlay của macOS khi cài đặt "Tự động"); font macOS lộ.
- Probe persona Linux: WebGL lộ `ANGLE Metal Renderer: Apple M1 Pro`, nên tổ hợp này bị từ chối.
- Trang kiểm tra công khai (headed và headless, persona macOS): sannysoft pass toàn bộ, vượt Cloudflare challenge, BrowserScan "Normal", CreepJS 0% headless.

## Giới hạn đã biết

- Font là font của máy chủ. Persona khác OS sẽ lộ qua đo font.
- Ảnh render WebGL (pixel) vẫn từ GPU thật; chỉ chuỗi vendor/renderer và tham số được giả.
- WebRTC không có candidate host dạng mDNS như Chrome thật (fork tắt). Không lộ IP, nhưng là một điểm khác biệt nhỏ.
- `userAgentData.fullVersionList` báo bản vá do fork chọn (vd. 148.0.7778.97), không phải số build thật.
- Chưa kiểm chứng trên Linux; bản `.dmg` chỉ giải nén được trên macOS và chỉ chạy trên Apple Silicon.
- Persona macOS luôn báo `devicePixelRatio` 1, trong khi MacBook thật gần như luôn là 2 (Retina). Ở headless, `availHeight` bằng `height` (không trừ thanh menu).
- Persona Windows trên macOS: scrollbar 0px. Đặt `defaults write org.chromium.Chromium AppleShowScrollBars Always` đưa về 15px (Windows thật 17px), nhưng cài đặt đó áp dụng cho mọi Chromium cùng bundle id trên máy.
- Phát hiện qua thời gian phản hồi CDP chưa được xử lý.
- Proxy bridge nghe trên `127.0.0.1` cổng ngẫu nhiên, không có mật khẩu (Chromium không gửi được). Trang web không dùng được nó (không gửi được `CONNECT`, request thường bị trả 400), nhưng tiến trình khác trên cùng máy có thể đi ra ngoài qua proxy của profile trong lúc profile đang mở.
- Phụ thuộc fork bên ngoài: nâng phiên bản phải chạy lại toàn bộ test (đặc biệt `test_emoji_canvas_does_not_crash`) trước khi đổi `DEFAULT_VERSION`.
