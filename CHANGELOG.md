# Changelog

Định dạng theo [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/); phiên bản theo [Semantic Versioning](https://semver.org/lang/vi/).

## [Unreleased]

### Thêm
- Điều khiển trang: upload file vào ô chọn file (kể cả ô ẩn) qua `POST /page/upload` và MCP `browser_upload`; chỉ nhận file nằm trong thư mục `media_outbox` (đổi bằng `TQD_UPLOAD_DIR`), từ chối file ngoài thư mục, file thiếu và định dạng không phải ảnh/video.
- Chờ URL hoặc chữ xuất hiện (`/page/wait-url`, `/page/wait-text`, MCP `browser_wait_for_url`, `browser_wait_for_text`) và cuộn trang (`/page/scroll`, MCP `browser_scroll`).
- Snapshot gọn: `interactive_only=true` chỉ giữ nút, link và ô nhập, giúp agent tốn ít token hơn.
- Gói `tqd_automation`: client REST cho từng profile, Judge nhận diện trạng thái trang (checkpoint, captcha, chưa đăng nhập...) và kiểm tra nội dung trước khi đăng (heuristic, thêm TypeSafe khi có `TYPESAFE_API_KEY`; ghi cả hai kết quả vào `automation_data/judge_*.jsonl`), cùng các cổng an toàn: kill switch, khoá sau checkpoint, giới hạn số bài mỗi ngày, khoảng cách tối thiểu và chặn bài trùng. Bài đã bấm Đăng nhưng chưa xác nhận vẫn được tính, nên không bao giờ đăng lặp.

### Sửa
- App desktop: nút "Launch" không còn bị gãy chữ thành hai dòng khi dùng giao diện English.
- Proxy dạng `host:port:user:pass` có `@` hoặc `:` trong mật khẩu không còn bị bỏ qua (trước đây profile mở mà không qua proxy). Chấp nhận proxy IPv6 dạng `[2001:db8::1]`; host proxy tối đa 253 ký tự.
- Tên profile không phân biệt hoa thường: "Demo" và "demo" không còn tạo được hai profile dùng chung một thư mục dữ liệu trên Windows/macOS. Đổi tên chỉ khác hoa thường vẫn giữ nguyên dữ liệu; tên chứa ký tự điều khiển bị từ chối.
- Đổi tên profile sang tên có thư mục dữ liệu sót lại trả về lỗi 409 thay vì làm hỏng danh sách profile. `profiles.json` được ghi nguyên tử, và các thao tác đồng thời (API, MCP, app) không còn ghi đè lẫn nhau, gây lỗi 500 hay xoá nhầm thư mục của profile vừa tạo lại.
- Proxy không vào được mạng báo lỗi dễ hiểu ("no internet connection through proxy host:port") thay vì chuỗi lỗi nội bộ; chi tiết vẫn có trong log.
- MCP `update_profile(proxy="")` xoá được proxy.
- Điều khiển trang từ chối cả scheme bị mã hoá phần trăm (`%66ile:`) và URL hỏng như `[::1`.
- Web panel: xác nhận "New fingerprint" không còn đóng luôn hộp thoại cookie; Esc đóng màn hình xem trực tiếp và đúng hộp thoại trên cùng; hiện lỗi kèm nút Thử lại khi không kết nối được server thay vì trang trắng; nút Lưu và các thao tác cookie bị khoá khi đang chạy; lỗi 422 hiển thị dễ đọc.
- App desktop: hỏi xác nhận trước khi tạo fingerprint mới; ô chọn ở tiêu đề bảng không còn bỏ chọn các profile ở trang khác; rail hiện số profile và số trình duyệt đang chạy; hộp thoại xoá nói rõ cookie và dữ liệu sẽ mất vĩnh viễn.

### Thay đổi
- Ngôn ngữ giao diện mặc định của app desktop và web panel là English; đặt `FOXPROFILE_LANG=vi` (hoặc bấm "Tiếng Việt" trong app) để dùng tiếng Việt.

## [2.3.1] - 2026-10-09

### Sửa
- Web panel: bảng profile không còn tràn mất cột thao tác (Mở/Dừng) khi cửa sổ trình duyệt hẹp hơn khoảng 1460px; bảng giờ đổi bố cục theo bề rộng thực của chính nó.
- Profile không còn kẹt ở trạng thái "Đang mở" trên app desktop khi cùng lúc được mở qua API hoặc MCP; hai lệnh mở đồng thời cho cùng một profile không còn khởi chạy hai trình duyệt.

## [2.3.0] - 2026-10-09

### Thay đổi
- Thiết kế lại giao diện app desktop và web panel theo một hệ thống chung (xem `DESIGN.md`): nền giấy sáng, rail xanh, bảng profile thẳng cột với cột Thiết bị / Proxy / Timezone · Locale, và "dấu" trạng thái (đang chạy, đang mở, lỗi) phân biệt bằng cả hình dạng lẫn màu. Font Be Vietnam Pro và JetBrains Mono được đóng gói sẵn (OFL), chạy được không cần mạng.
- Thêm bộ lọc profile kèm số đếm (tất cả, đang chạy, có/không proxy, engine Chrome) trên cả hai giao diện; web panel có thêm thao tác hàng loạt và hộp thoại xác nhận riêng; app desktop đổi được Tiếng Việt / English ngay khi đang chạy.
- Thuật ngữ chuyên ngành giữ tiếng Anh trong giao diện tiếng Việt (fingerprint, engine, timezone, locale).

### Thêm
- Nhân **Chrome (thử nghiệm)** bên cạnh Camoufox, dựa trên fingerprint-chromium: chọn khi tạo profile trên app, web panel, REST API (`"engine": "chrome"`) và MCP (`create_profile(engine="chrome")`). Nhân cố định sau khi tạo. Cookie, fingerprint, điều khiển trang, mở lại tab và Kiểm tra IP dùng được như profile Camoufox. Bản trình duyệt được tự tải ở nền khi tạo profile Chrome đầu tiên, hoặc lúc mở profile nếu chưa có (cũng tải tay được bằng `python -m chrome_engine fetch`).
- Proxy dạng `host:port:user:pass` (định dạng thường gặp của nhà bán proxy) được chấp nhận ở mọi nơi nhập proxy, kể cả có tiền tố `socks5://`.
- Mở lại các tab đang mở khi profile được dừng (lưu vào `camoufox_data/<profile>/tabs.json` mỗi 2 giây khi tab thay đổi, chỉ `http`/`https`, tối đa 30 tab). Tắt bằng `FOXPROFILE_RESTORE_TABS=false`.

### Sửa
- Rò rỉ DNS khi dùng proxy `socks5://`/`socks4://`: việc tra IP đi ra lúc mở profile và nút **Kiểm tra IP** từng phân giải tên miền bằng DNS của máy (lộ nhà mạng thật). Nay chuyển sang `socks5h://`/`socks4a://` để proxy phân giải. Bản thân trình duyệt không bị ảnh hưởng.
- Chế độ `HEADLESS=virtual` (server Linux) không còn bỏ sót tiến trình Xvfb khi profile mở lỗi (ví dụ proxy không vào được) hoặc khi runner bị kill cứng/crash. Runner tự quản lý màn hình ảo và ghi lại Xvfb nó đã bật (theo PID và thời điểm khởi động, trong thư mục tạm riêng của user) để launcher, hoặc lần mở sau, tắt đúng Xvfb đó.

## [2.2.0] - 2026-10-08

### Thêm
- Đặt cố định múi giờ (IANA) và ngôn ngữ (`vi-VN`) cho từng profile; để trống vẫn tự động theo IP.
- Nút **Kiểm tra IP**: đối chiếu IP đi ra với Cloudflare, ipinfo và ip-api, cảnh báo lệch quốc gia/múi giờ, IP datacenter, proxy dual-stack và ngôn ngữ ngẫu nhiên. Có trên app, web panel, REST API (`GET /profiles/{name}/ip-check`, `POST /proxy/geo-check`) và MCP (`check_profile_ip`).
- Hướng dẫn triển khai lên server Linux (`docs/DEPLOY.md`, `deploy/`) và các script e2e thủ công (`tests/e2e/`).

## [2.1.0] - 2026-10-08

### Thêm
- MCP server (27 tool) cho AI agent, qua stdio và qua HTTP tại `/mcp`.
- Web panel có token bảo vệ, xem và điều khiển màn hình trình duyệt từ xa.
- Server mode chạy ẩn trình duyệt (`python -m src.server`).
- Hộp thoại hướng dẫn kết nối MCP cho Claude Code, Cursor, VS Code và Claude Desktop.

### Sửa
- Server mode đọc đúng `FOXPROFILE_HEADLESS` từ `.env`.

## [2.0.0] - 2026-10-08

Phát hành đầu tiên của FoxProfile: vân tay cố định theo profile, proxy riêng, xuất/nhập cookie (JSON và Netscape), REST API, giao diện tiếng Việt/tiếng Anh.

[Unreleased]: https://github.com/chienbm98/foxprofile/compare/v2.3.1...HEAD
[2.3.1]: https://github.com/chienbm98/foxprofile/compare/v2.3.0...v2.3.1
[2.3.0]: https://github.com/chienbm98/foxprofile/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/chienbm98/foxprofile/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/chienbm98/foxprofile/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/chienbm98/foxprofile/releases/tag/v2.0.0
