# End-to-end scripts

Chạy thủ công với một FoxProfile thật (không thuộc `pytest`/CI vì cần trình duyệt và mạng).

| Script | Cần gì | Kiểm tra |
| --- | --- | --- |
| `api_e2e.py` | API đang chạy | vân tay cố định, cookie JSON/Netscape, launch thành công/thất bại |
| `control_e2e.py` | không (tự chạy launcher, headless) | điều khiển trang: navigate, snapshot, click, tab, chặn `file://` |
| `mcp_stdio_e2e.py` | API đang chạy | MCP qua stdio (`python -m src.mcp_server`) |
| `mcp_http_e2e.py` | API đang chạy | MCP qua HTTP tại `/mcp`, 401 khi thiếu token |
| `panel_e2e.py` | API + web panel | đăng nhập, tạo/sửa profile, xem màn hình từ xa |
| `mcp_guide_e2e.py` | API + web panel | hộp thoại "Kết nối AI (MCP)" |
| `detection_e2e.py headless headed` | mạng | so headless/có cửa sổ trên các trang kiểm tra bot |

Biến môi trường:

```bash
FOXPROFILE_URL=http://127.0.0.1:8000     # địa chỉ FoxProfile
FOXPROFILE_API_TOKEN=...                 # nếu server có token
FOXPROFILE_DATA_DIR=camoufox_data        # api_e2e đọc fingerprint.json ở đây
E2E_OUT=e2e-output                       # nơi lưu ảnh chụp
```

Các script tạo profile tên `e2e-*`, `mcp-demo`, `http-demo`, `panel-demo`, `ctl-test`; nên chạy với một thư mục dữ liệu riêng (`FOXPROFILE_DATA_DIR`, `FOXPROFILE_PROFILES_FILE`) thay vì dữ liệu thật.
