# Changelog

Định dạng theo [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/); phiên bản theo [Semantic Versioning](https://semver.org/lang/vi/).

## [Unreleased]

### Thêm
- WebRTC trên Camoufox không còn lộ IP thật khi dùng proxy hoặc Proton VPN. Nguyên nhân là Camoufox spoof IP WebRTC theo `geoip` (IP thật trước khi VPN kết nối) và STUN vẫn đi ra ngoài proxy; profile Proton giờ không truyền `geoip` cho WebRTC và đặt `ice.proxy_only`/`no_host`/`default_address_only`, nên không phát candidate chứa IP máy. Chrome đã có chính sách tương đương.
- Kiểu kết nối theo từng profile: ô **Proxy** trong form profile thành dropdown **Trực tiếp / Proxy / Proton VPN**. Chọn Proxy thì hiện ô proxy như cũ; chọn Proton VPN thì nhập username, password, secret TOTP (nếu bật 2FA) và quốc gia exit riêng của profile đó. Profile Proton được cài extension (add-on Firefox đã ký cho Camoufox, bản Chrome Web Store nạp bằng `--load-extension` cho fingerprint-chromium) và tự đăng nhập; chuyển về Trực tiếp/Proxy thì extension được gỡ ở lần mở sau. Tài khoản Proton lưu riêng từng profile trong `proton_accounts.json` (mật khẩu mã hoá bằng key cục bộ), không ghi vào `profiles.json`, log hay file xuất profile. Engine Chrome tự bấm Sign in và điền trang account; Camoufox mở các trang riêng của extension qua Marionette nên cũng tự bấm Sign in, điền account/TOTP và kết nối quốc gia đã chọn. Profile chỉ được báo sẵn sàng sau khi VPN kết nối; nếu đăng nhập hoặc kết nối thất bại, trình duyệt tự đóng và lần mở báo `LAUNCH_FAILED`. Captcha hoặc 2FA thiếu secret làm lần mở thất bại thay vì để trình duyệt chạy ở IP thật. Thời gian API chờ mở profile mặc định tăng lên 180 giây để đủ cho lần đăng nhập đầu tiên. Thêm CLI `python -m src.services.proton_session prepare <profile> --country US` để đăng nhập/kết nối trước khi mở browser (Chrome), cùng `harvest`/`inject` session qua file `0600`.

### Bảo mật
- `FOXPROFILE_API_HOST` để trống không còn vượt qua kiểm tra bind: giá trị rỗng giờ là `127.0.0.1`, và một host rỗng khi kiểm tra bind được coi là mọi giao diện, nên bắt buộc có token. Trước đây API có thể lắng nghe mọi giao diện mà không cần token.
- Mật khẩu và TOTP secret của tài khoản Proton đều được mã hoá. Khoá (`proton_accounts.key`) và file tài khoản không bao giờ bị thay thế khi không đọc được; thao tác ghi báo lỗi thay vì làm mất mọi mật khẩu đã lưu.
- Proxy bridge của engine Chrome chỉ phục vụ client gửi đúng thông tin xác thực của lần mở đó; client khác nhận 407.
- Extension Chrome của Proton VPN được kiểm tra chữ ký CRX3 trước khi giải nén. Chỉ chấp nhận CRX3.
- Web panel chỉ giữ API token trong `sessionStorage` (xoá khi đóng tab). Token do bản cũ lưu trong `localStorage` được xoá khi mở panel.

### Sửa
- Xoá, đổi tên, xuất kèm dữ liệu, nhập ghi đè và đặt lại fingerprint không còn chạy khi trình duyệt của profile đang mở: API trả 409, app báo "hãy dừng trình duyệt trước".
- Ghi `profiles.json` thất bại được báo lỗi (API trả 500) và thay đổi được hoàn tác. Trước đây API báo thành công nhưng thay đổi mất khi khởi động lại.
- Xoá profile không còn xoá dữ liệu khi lưu danh sách thất bại.
- `profiles.json` không đọc được được sao lưu thành `profiles.json.corrupt-<thời gian>` trước khi lần ghi tiếp theo thay thế nó.
- Điều khiển trình duyệt và MCP gọi `127.0.0.1` không còn đi qua `HTTP_PROXY` của máy.
- Nhập profile từ file zip kiểm tra hệ điều hành và proxy giống như khi tạo mới.
- Danh sách profile đọc file tài khoản Proton một lần cho cả danh sách thay vì một lần cho mỗi profile.

### Thay đổi
- `camoufox` được giới hạn `<0.6`. `tests/test_camoufox_contract.py` kiểm tra các API nội bộ mà FoxProfile dùng; nếu một bản Camoufox không còn bộ chọn locale, lần mở báo lỗi rõ ràng thay vì chọn locale ngẫu nhiên.
- CI chạy thêm Python 3.14.
- Địa chỉ placeholder trong test dùng dải tài liệu (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24) theo CLAUDE.md.

### Giới hạn đã biết
- Marionette, kênh điều khiển extension Proton trong Camoufox, không có xác thực. Nó chỉ nghe trên `127.0.0.1` với cổng ngẫu nhiên, nên tiến trình khác trên cùng máy có thể kết nối tới cổng đó trong lúc profile Proton đang mở.

## [2.4.0] - 2026-10-30

### Thay đổi
- Engine Chrome không còn là thử nghiệm: bỏ nhãn "experimental"/"thử nghiệm" trong app, web panel, API và MCP. README có mục "Giới hạn đã biết" (font lấy từ máy, kích thước màn hình thật khi chạy có cửa sổ, không có Widevine, ghim bản 148, WebRTC khi có proxy).
- Locale tự động được chọn một lần cho mỗi quốc gia rồi giữ cố định theo profile (file `geo_locale.json` trong thư mục profile), trên cả Camoufox và Chrome. Trước đây locale bị chọn lại ngẫu nhiên ở mỗi lần mở, nên cùng một tài khoản có thể hôm nay là `en-US`, hôm sau là `es-US`. Locale này đi kèm khi xuất profile và bị xoá khi tạo fingerprint mới.
- Kiểm tra IP không còn cảnh báo "locale ngẫu nhiên"; khi kiểm tra theo profile (`/profiles/{name}/ip-check`, MCP `check_profile_ip`) kết quả hiện locale mà profile đang giữ.
- Ngôn ngữ giao diện mặc định của app desktop và web panel là English; đặt `FOXPROFILE_LANG=vi` (hoặc bấm "Tiếng Việt" trong app) để dùng tiếng Việt.

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

[Unreleased]: https://github.com/chienbm98/foxprofile/compare/v2.4.0...HEAD
[2.4.0]: https://github.com/chienbm98/foxprofile/compare/v2.3.1...v2.4.0
[2.3.1]: https://github.com/chienbm98/foxprofile/compare/v2.3.0...v2.3.1
[2.3.0]: https://github.com/chienbm98/foxprofile/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/chienbm98/foxprofile/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/chienbm98/foxprofile/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/chienbm98/foxprofile/releases/tag/v2.0.0
