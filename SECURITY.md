# Chính sách bảo mật

## Báo cáo lỗ hổng

**Không mở issue công khai cho lỗ hổng bảo mật.** Hãy báo riêng qua tab **Security → Report a vulnerability** của repo (GitHub Private Vulnerability Reporting).

Vui lòng ghi rõ:

- Mô tả lỗ hổng và ảnh hưởng
- Các bước tái hiện
- Phiên bản hoặc commit bị ảnh hưởng

Maintainer sẽ phản hồi trong vòng 7 ngày và công bố bản sửa trước khi công khai chi tiết.

## Phạm vi đáng chú ý

FoxProfile lưu cookie đăng nhập và proxy của nhiều tài khoản, nên các lỗi sau được ưu tiên cao nhất:

- Đọc hoặc ghi file ngoài thư mục dữ liệu (path traversal qua tên profile hay file ZIP nhập vào)
- Lộ cookie, proxy hoặc mật khẩu proxy ra log hay ra ngoài máy
- Khiến REST API nghe ngoài `127.0.0.1` khi người dùng không chủ động cấu hình

## Lưu ý cho người dùng

- REST API **không có xác thực**. Giữ `FOXPROFILE_API_HOST=127.0.0.1`.
- Thư mục `camoufox_data/` chứa cookie đăng nhập. Không chia sẻ và không commit.
- Chỉ nhập profile ZIP hay file cookie từ nguồn bạn tin tưởng.
