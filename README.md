<div align="center">
  <img src="src/assets/icon.png" width="112" alt="FoxProfile logo" />
  <h1>FoxProfile</h1>
  <p><strong>Quản lý nhiều profile trình duyệt chống phát hiện, miễn phí và mã nguồn mở</strong></p>
  <p>Mỗi profile có vân tay thiết bị, cookie và proxy riêng · Giao diện tiếng Việt · Có REST API để tự động hóa</p>
  <p>Tiếng Việt · <a href="README.en.md">English</a></p>
</div>

![FoxProfile](docs/images/main.png)

FoxProfile là ứng dụng desktop quản lý profile cho [Camoufox](https://github.com/daijro/camoufox), một bản Firefox đã được chỉnh sửa ở tầng mã nguồn để giả lập vân tay thiết bị. Nó là lựa chọn tự host, chạy trên máy bạn, thay cho các antidetect browser trả phí như GoLogin, GPM hay MoreLogin.

## Tính năng

- **Vân tay cố định cho từng profile.** Lần mở đầu tiên sinh ra một thiết bị (màn hình, GPU, số nhân CPU, font, nhiễu canvas/audio) và lưu lại; các lần sau mở lại đúng thiết bị đó. Có thể chủ động đổi sang thiết bị mới.
- **Mỗi profile một proxy riêng**, hỗ trợ HTTP/HTTPS/SOCKS4/SOCKS5 có hoặc không có mật khẩu, có nút kiểm tra proxy. Múi giờ và ngôn ngữ tự khớp theo IP, hoặc đặt cố định cho từng profile; nút **Kiểm tra IP** đối chiếu IP ra với Cloudflare, ipinfo, ip-api và cảnh báo khi lệch quốc gia/múi giờ hoặc IP bị gắn datacenter.
- **Xuất/nhập cookie**
  - JSON theo định dạng Cookie-Editor / EditThisCookie: dùng được với GoLogin, GPM, Multilogin và extension Cookie-Editor.
  - `cookies.txt` (Netscape): dùng được với yt-dlp, curl, wget.
- **Xuất/nhập cả profile** ra file ZIP để chuyển sang máy khác, có hoặc không kèm dữ liệu trình duyệt. Vân tay luôn đi kèm.
- **Thao tác hàng loạt**: chọn nhiều profile để mở, dừng hoặc xóa cùng lúc.
- **Tìm kiếm** profile theo tên hoặc proxy. Thẻ profile hiện proxy (đã ẩn mật khẩu) và thiết bị đang giả lập.
- **MCP server**: Claude, Cursor... tự mở profile, lướt web, click, gõ, chụp màn hình.
- **Chế độ server + web panel**: chạy trên VPS, quản lý và xem màn hình từ xa qua trình duyệt, có token bảo vệ.
- **REST API** để điều khiển bằng script, có trang tài liệu Swagger.
- Giao diện **tiếng Việt** (mặc định) và tiếng Anh.

## Cài đặt

Cần Python 3.10 trở lên.

```bash
git clone https://github.com/chienbm98/foxprofile.git
cd foxprofile

python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
python -m camoufox fetch
```

`camoufox fetch` tải bản trình duyệt Camoufox (vài trăm MB) từ GitHub của dự án Camoufox. Lần mở profile đầu tiên sẽ tải thêm cơ sở dữ liệu GeoIP (~50 MB).

## Chạy

```bash
python -m src.main
```

Trên Windows có thể bấm đúp `run_foxprofile.bat`.

Ứng dụng mở cửa sổ quản lý và đồng thời chạy API tại `http://127.0.0.1:8000`. Tài liệu API: `http://127.0.0.1:8000/docs`.

## Múi giờ, ngôn ngữ và Kiểm tra IP

Mặc định, mỗi lần mở profile Camoufox tra IP đi ra (qua proxy của profile) và đặt múi giờ, ngôn ngữ, toạ độ và IP WebRTC theo IP đó. Có ba điều nên biết:

- **Ngôn ngữ tự động được chọn ngẫu nhiên ở mỗi lần mở**, theo tỷ lệ người nói từng ngôn ngữ ở quốc gia của IP. Ví dụ IP Pháp cho `fr-FR` khoảng 60% số lần, còn lại là `en-FR`, `es-FR`… Một tài khoản đổi ngôn ngữ giữa các phiên là điều đáng ngờ, nên hãy đặt cố định ngôn ngữ cho profile.
- **Các cơ sở dữ liệu GeoIP không phải lúc nào cũng thống nhất.** Cùng một IP có thể được Cloudflare xếp vào nước này, Google vào nước khác; Camoufox cũng có thể chọn một múi giờ cùng giờ nhưng khác tên (ví dụ IP Việt Nam ra `Asia/Bangkok` thay vì `Asia/Ho_Chi_Minh`).
- **IP datacenter dễ bị bắt captcha** bất kể cấu hình trình duyệt. Với các trang dùng Cloudflare, proxy residential hoặc 4G quan trọng hơn mọi tinh chỉnh khác.

Trong hộp thoại tạo/sửa profile có hai ô **Múi giờ** (tên IANA, ví dụ `Asia/Ho_Chi_Minh`) và **Ngôn ngữ** (dạng `vi-VN`); để trống là tự động theo IP. Nút **Kiểm tra IP** lấy IP đi ra qua proxy, đối chiếu với Cloudflare, ipinfo và ip-api, rồi cảnh báo khi lệch quốc gia hoặc múi giờ, khi IP bị gắn datacenter, khi proxy ra Internet bằng IPv4 và IPv6 khác nhau, và khi ngôn ngữ đang để ngẫu nhiên.

## Chế độ server và web panel (chạy trên VPS)

Không cần cửa sổ desktop: chỉ chạy API và web panel, trình duyệt chạy ẩn.

```bash
python -m src.server                     # http://127.0.0.1:8000
python -m src.server --host 0.0.0.0      # mở ra mạng: BẮT BUỘC đặt token
```

Mở `http://<địa-chỉ>:8000/` để vào **web panel**: tạo, sửa, mở/dừng profile, xuất/nhập cookie và **xem màn hình từ xa**. Bạn có thể bấm thẳng lên ảnh màn hình và gõ phím để tự đăng nhập hay giải captcha, kể cả khi trình duyệt đang chạy ẩn trên server.

![Web panel](docs/images/panel.png)

![Xem màn hình từ xa](docs/images/panel-viewer.png)

**Bảo mật:** khi nghe ngoài `127.0.0.1`, server **từ chối khởi động** nếu chưa đặt `FOXPROFILE_API_TOKEN` (tối thiểu 24 ký tự). Web panel, REST API và MCP đều dùng chung token này.

```bash
# Tạo token ngẫu nhiên
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Khi đưa lên VPS, nên đặt server sau reverse proxy có HTTPS (Caddy, Nginx) để token không bị gửi đi dưới dạng chữ thường. Trên Linux không có màn hình, đặt `FOXPROFILE_HEADLESS=virtual` (cần cài `xvfb`) để trình duyệt chạy trên màn hình ảo, khó bị phát hiện hơn chế độ headless thường.

## MCP: cho AI điều khiển trình duyệt

FoxProfile có sẵn MCP server, để Claude Code, Claude Desktop, Cursor, VS Code... tự quản lý profile và thao tác trên trang: mở URL, đọc trang, click, gõ, chụp màn hình.

**Cách nhanh nhất:** bấm **🤖 Kết nối AI (MCP)** trên app desktop hoặc web panel. Hộp thoại sinh sẵn cấu hình cho từng ứng dụng AI, đúng địa chỉ và token của bạn, chỉ cần bấm Sao chép rồi dán.

![Kết nối AI (MCP)](docs/images/mcp-guide.png)

MCP được phục vụ qua HTTP tại `/mcp`, ngay trên cổng của FoxProfile, nên dùng được cả khi FoxProfile chạy trên VPS:

```bash
# Claude Code
claude mcp add --transport http foxprofile http://127.0.0.1:8000/mcp
# Server có token:
claude mcp add --transport http foxprofile https://vps.cua-ban.com/mcp --header "Authorization: Bearer <token>"
```

```json
// Cursor: ~/.cursor/mcp.json
{ "mcpServers": { "foxprofile": { "url": "http://127.0.0.1:8000/mcp" } } }
```

Claude Desktop chỉ chạy được server MCP cục bộ: dùng `foxprofile_mcp.py` (cùng máy) hoặc cầu nối `npx mcp-remote` (máy khác). Hộp thoại "Kết nối AI" sinh sẵn cả hai.

Sau đó chỉ cần nhắn AI, ví dụ: *"Mở profile tiktok-us-02, vào tiktok.com và chụp màn hình cho tôi"*.

| Nhóm | Tool |
| --- | --- |
| Profile | `list_profiles`, `get_profile`, `create_profile`, `update_profile`, `launch_profile`, `stop_profile`, `running_profiles` |
| Cookie & vân tay | `export_cookies`, `import_cookies`, `get_fingerprint`, `reset_fingerprint`, `check_proxy`, `check_profile_ip` |
| Trang | `browser_navigate`, `browser_back`, `browser_snapshot`, `browser_get_text`, `browser_click`, `browser_click_at`, `browser_type`, `browser_press`, `browser_wait_for`, `browser_screenshot`, `browser_evaluate` |
| Tab | `browser_tabs`, `browser_tab_new`, `browser_tab_select`, `browser_tab_close` |

MCP **không** có tool xóa profile, để AI không thể vô tình xóa cookie của tài khoản. Trang chỉ mở được `http`, `https` và `about:blank`; `file://` và `about:config` bị chặn.

## Cookie và vân tay

![Cookie & vân tay](docs/images/cookies.png)

Bấm biểu tượng 🍪 trên thẻ profile. **Trình duyệt của profile phải đang tắt**, vì FoxProfile mở profile ở chế độ ẩn để đọc và ghi cookie.

- Cookie phiên (session) khi nhập vào sẽ được đặt hạn 1 năm. Nếu không, Firefox sẽ xóa chúng ngay khi đóng trình duyệt.
- "Đổi vân tay" xóa vân tay đã lưu; lần mở sau profile sẽ là một thiết bị khác. Đổi hệ điều hành của profile cũng tự sinh vân tay mới.

## Cấu hình

Mọi cấu hình đều không bắt buộc. Muốn đổi thì sao chép `.env.example` thành `.env`.

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `FOXPROFILE_LANG` | `vi` | Ngôn ngữ giao diện: `vi` hoặc `en` |
| `FOXPROFILE_PROFILES_FILE` | `profiles.json` | File lưu danh sách profile |
| `FOXPROFILE_DATA_DIR` | `camoufox_data` | Thư mục dữ liệu, mỗi profile một thư mục con |
| `FOXPROFILE_LOG_DIR` | `logs` | Thư mục log |
| `FOXPROFILE_LOG_LEVEL` | `INFO` | Mức log |
| `FOXPROFILE_PROXY_TIMEOUT` | `10` | Thời gian chờ khi kiểm tra proxy (giây) |
| `FOXPROFILE_LAUNCH_TIMEOUT` | `90` | Thời gian API chờ trình duyệt mở xong (giây) |
| `FOXPROFILE_HEADLESS` | `false` (`true` ở chế độ server) | Chạy trình duyệt ẩn: `true`, `false` hoặc `virtual` (Linux + Xvfb) |
| `FOXPROFILE_API_TOKEN` | *(trống)* | Token cho API, web panel và MCP. Bắt buộc khi API nghe ngoài `127.0.0.1` |
| `FOXPROFILE_API_HOST` | `127.0.0.1` | Địa chỉ API |
| `FOXPROFILE_API_PORT` | `8000` | Cổng API |

## Dữ liệu được lưu ở đâu

```text
profiles.json                         danh sách profile (tên, proxy, hệ điều hành)
camoufox_data/<tên-profile>/          dữ liệu trình duyệt: cookie, lịch sử, localStorage
camoufox_data/<tên-profile>/fingerprint.json   vân tay thiết bị của profile
logs/foxprofile_YYYYMMDD.log          log theo ngày
```

> ⚠️ `camoufox_data/` chứa cookie đăng nhập của mọi tài khoản. Không commit, không chia sẻ thư mục này.

## REST API

Tiền tố: `/api/v1`. Xem đầy đủ tại `/docs` khi ứng dụng đang chạy.

| Method | Đường dẫn | Mô tả |
| --- | --- | --- |
| `GET` | `/health` | Kiểm tra API |
| `GET` / `POST` | `/profiles` | Liệt kê / tạo profile |
| `GET` / `PATCH` / `DELETE` | `/profiles/{name}` | Xem / sửa / xóa profile |
| `POST` | `/profiles/{name}/export` | Xuất profile ra ZIP |
| `POST` | `/profiles/import` | Nhập profile từ ZIP |
| `GET` | `/profiles/{name}/cookies?format=json\|netscape` | Xuất cookie |
| `POST` | `/profiles/{name}/cookies` | Nhập cookie (`{"content": "<JSON hoặc cookies.txt>"}`) |
| `GET` / `DELETE` | `/profiles/{name}/fingerprint` | Xem / đổi vân tay |
| `GET` | `/browser` | Danh sách profile đang chạy |
| `POST` | `/browser/{name}/launch` | Mở trình duyệt, chờ đến khi mở xong hoặc lỗi |
| `POST` | `/browser/{name}/stop` | Đóng trình duyệt |
| `POST` | `/proxy/check` | Kiểm tra proxy |
| `GET` | `/profiles/{name}/ip-check` | Kiểm tra IP ra của profile: quốc gia, múi giờ theo Cloudflare/ipinfo/ip-api, cảnh báo lệch |
| `POST` | `/proxy/geo-check` | Như trên cho tổ hợp `{proxy, timezone, locale}` chưa lưu |
| `POST` | `/browser/{name}/page/navigate` | Mở URL trong tab đang chọn |
| `GET` | `/browser/{name}/page/snapshot` | Cây accessibility của trang (để chọn selector) |
| `POST` | `/browser/{name}/page/click` · `type` · `press` · `wait` | Click, gõ, bấm phím, chờ phần tử (selector Playwright) |
| `POST` | `/browser/{name}/page/click-at` · `keyboard` | Click theo tọa độ, gõ vào ô đang chọn |
| `GET` | `/browser/{name}/page/screenshot` | Ảnh PNG của tab (`?format=json` để nhận base64) |
| `POST` | `/browser/{name}/page/evaluate` | Chạy JavaScript |
| `GET` / `POST` / `DELETE` | `/browser/{name}/page/tabs` | Quản lý tab |

Ví dụ:

```bash
# Tạo profile macOS có proxy
curl -X POST http://127.0.0.1:8000/api/v1/profiles \
  -H "Content-Type: application/json" \
  -d '{"name": "tiktok-us-02", "os_type": "macos", "proxy": "socks5://user:pass@1.2.3.4:1080"}'

# Mở trình duyệt. Trả 200 khi đã mở, 502 kèm lý do nếu lỗi.
# Thêm ?wait=false để trả về ngay (202).
curl -X POST http://127.0.0.1:8000/api/v1/browser/tiktok-us-02/launch

# Xuất cookie dạng cookies.txt
curl "http://127.0.0.1:8000/api/v1/profiles/tiktok-us-02/cookies?format=netscape" -o cookies.txt
```

Khi có `FOXPROFILE_API_TOKEN`, mọi request (trừ `/health` và `/info`) phải gửi header `Authorization: Bearer <token>`.

## Định dạng proxy

`host:port`, `http://host:port`, `https://...`, `socks4://...`, `socks5://...`, có thể kèm `user:pass@`. Để trống nghĩa là kết nối trực tiếp.

## Lưu ý sử dụng

Antidetect browser là công cụ hợp pháp, thường dùng để bảo vệ quyền riêng tư, kiểm thử web, hoặc để agency quản lý tài khoản của nhiều khách hàng. Tuy vậy, dùng nhiều tài khoản trên cùng một nền tảng có thể vi phạm điều khoản của Facebook, TikTok, Google, Shopee... Bạn tự chịu trách nhiệm về cách mình sử dụng.

## Giấy phép

[MIT](LICENSE). Copyright (c) 2026 chienbm98.
