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
- **Mỗi profile một proxy riêng**, hỗ trợ HTTP/HTTPS/SOCKS4/SOCKS5 có hoặc không có mật khẩu, có nút kiểm tra proxy. Múi giờ và ngôn ngữ tự khớp theo IP.
- **Xuất/nhập cookie**
  - JSON theo định dạng Cookie-Editor / EditThisCookie: dùng được với GoLogin, GPM, Multilogin và extension Cookie-Editor.
  - `cookies.txt` (Netscape): dùng được với yt-dlp, curl, wget.
- **Xuất/nhập cả profile** ra file ZIP để chuyển sang máy khác, có hoặc không kèm dữ liệu trình duyệt. Vân tay luôn đi kèm.
- **Thao tác hàng loạt**: chọn nhiều profile để mở, dừng hoặc xóa cùng lúc.
- **Tìm kiếm** profile theo tên hoặc proxy. Thẻ profile hiện proxy (đã ẩn mật khẩu) và thiết bị đang giả lập.
- **REST API cục bộ** để điều khiển bằng script hoặc AI agent, có trang tài liệu Swagger.
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

> ⚠️ API **không có xác thực**. Chỉ để nó nghe trên `127.0.0.1`. Nếu đổi sang `0.0.0.0`, bất kỳ ai trong mạng cũng điều khiển được mọi profile và lấy được toàn bộ cookie.

## Định dạng proxy

`host:port`, `http://host:port`, `https://...`, `socks4://...`, `socks5://...`, có thể kèm `user:pass@`. Để trống nghĩa là kết nối trực tiếp.

## Lưu ý sử dụng

Antidetect browser là công cụ hợp pháp, thường dùng để bảo vệ quyền riêng tư, kiểm thử web, hoặc để agency quản lý tài khoản của nhiều khách hàng. Tuy vậy, dùng nhiều tài khoản trên cùng một nền tảng có thể vi phạm điều khoản của Facebook, TikTok, Google, Shopee... Bạn tự chịu trách nhiệm về cách mình sử dụng.

## Giấy phép

[MIT](LICENSE). Copyright (c) 2026 chienbm98.
