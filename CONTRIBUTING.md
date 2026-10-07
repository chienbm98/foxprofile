# Đóng góp cho FoxProfile

Cảm ơn bạn đã muốn đóng góp! Mọi đóng góp đều được chào đón: báo lỗi, đề xuất tính năng, sửa tài liệu, dịch thuật hay viết code.

*English speakers: issues and pull requests in English are welcome too.*

## Báo lỗi và đề xuất

- **Lỗi:** mở [issue mới](../../issues/new/choose) theo mẫu "Báo lỗi". Ghi rõ hệ điều hành, phiên bản Python, các bước tái hiện và trích đoạn log trong `logs/`.
- **Tính năng:** dùng mẫu "Đề xuất tính năng". Nên mở issue thảo luận trước khi viết code cho thay đổi lớn, để tránh làm xong mà không được nhận.
- **Lỗ hổng bảo mật:** đừng mở issue công khai. Xem [SECURITY.md](SECURITY.md).

> ⚠️ Trước khi đính kèm log hay file, hãy xóa cookie, proxy có mật khẩu và mọi thông tin tài khoản.

## Quy trình gửi Pull Request

1. **Fork** repo về tài khoản của bạn, rồi clone về máy.
2. **Tạo nhánh** từ `main`, đặt tên theo loại thay đổi:
   - `feat/<mô-tả>`: tính năng mới
   - `fix/<mô-tả>`: sửa lỗi
   - `docs/<mô-tả>`: tài liệu
   - `refactor/<mô-tả>`, `test/<mô-tả>`, `chore/<mô-tả>`
3. **Cài môi trường dev:**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # Windows
   source .venv/bin/activate       # Linux/macOS
   pip install -r requirements-dev.txt
   python -m camoufox fetch        # chỉ cần nếu muốn chạy thử app
   ```
4. **Viết code và test.** Sửa lỗi thì thêm test tái hiện lỗi đó. Thêm tính năng thì thêm test cho phần logic.
5. **Kiểm tra trước khi đẩy lên:**
   ```bash
   ruff check src tests
   ruff format --check src tests
   pytest
   ```
6. **Commit** theo chuẩn [Conventional Commits](https://www.conventionalcommits.org/):
   ```text
   feat(cookies): export cookies as Netscape cookies.txt
   fix(api): report failed launches with status 502
   docs: add proxy format examples
   ```
7. **Mở Pull Request** vào nhánh `main` và điền đủ mẫu PR. CI sẽ tự chạy lint và test trên Windows, Linux và macOS. PR chỉ được merge khi CI xanh và có ít nhất một maintainer duyệt.

## Quy ước code

- Python ≥ 3.10, có type hint cho hàm mới.
- Định dạng và lint bằng `ruff` (cấu hình trong `pyproject.toml`).
- **Chữ hiển thị trên giao diện không viết cứng** mà thêm vào `src/core/strings.py` ở **cả** `en` và `vi`, rồi gọi `get_string("key")`. Test sẽ báo lỗi nếu thiếu khóa ở một trong hai ngôn ngữ.
- Tên profile luôn phải đi qua `validate_profile_name` trước khi dùng làm đường dẫn.
- Không commit `profiles.json`, `camoufox_data/`, `logs/` hay file `.env`: chúng chứa cookie và proxy thật.

## Cấu trúc thư mục

```text
src/
  api/          REST API (FastAPI): routes, schemas
  core/         cấu hình, log, chuỗi đa ngôn ngữ
  models/       dataclass Profile
  services/
    browser/    khởi chạy Camoufox, vân tay, cookie
    profile/    lưu, xuất/nhập profile
    proxy/      kiểm tra proxy
  ui/           giao diện Flet: components, dialogs, actions
  utils/        kiểm tra tên, phân tích proxy
tests/          pytest
```

## Giấy phép

Khi gửi đóng góp, bạn đồng ý để đóng góp đó được phát hành theo [giấy phép MIT](LICENSE) của dự án.

Mọi người tham gia cần tuân theo [Quy tắc ứng xử](CODE_OF_CONDUCT.md).
