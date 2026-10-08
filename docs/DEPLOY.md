# Triển khai FoxProfile lên VPS (Ubuntu 24.04)

Chạy FoxProfile ở chế độ server (API, web panel, MCP) phía sau nginx có HTTPS, dưới một user hệ thống riêng. Cổng 8000 chỉ nghe trên `127.0.0.1`; mọi truy cập từ ngoài đi qua nginx và cần API token.

## 1. Gói hệ thống và user riêng

```bash
apt-get update
apt-get install -y git python3-venv xvfb libgtk-3-0t64 libx11-xcb1 libasound2t64 \
  libdbus-glib-1-2 certbot python3-certbot-nginx
useradd --system --create-home --home-dir /opt/foxprofile --shell /usr/sbin/nologin foxprofile
```

Ubuntu 22.04: dùng `libgtk-3-0` và `libasound2` (không có hậu tố `t64`).

## 2. Code, thư viện, trình duyệt

```bash
runuser -u foxprofile -- bash -c '
cd /opt/foxprofile
git clone https://github.com/chienbm98/foxprofile.git app
cd app
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m camoufox fetch
'
```

## 3. Cấu hình

```bash
TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
cat > /opt/foxprofile/app/.env <<EOF
FOXPROFILE_API_TOKEN=$TOKEN
FOXPROFILE_HEADLESS=virtual
FOXPROFILE_API_HOST=127.0.0.1
FOXPROFILE_API_PORT=8000
EOF
chown foxprofile:foxprofile /opt/foxprofile/app/.env && chmod 600 /opt/foxprofile/app/.env
chmod 750 /opt/foxprofile
echo "Token: $TOKEN"   # lưu vào trình quản lý mật khẩu
```

## 4. Service

```bash
cp deploy/foxprofile.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now foxprofile
curl -s http://127.0.0.1:8000/api/v1/info    # "headless":"virtual", "auth_required":true
```

## 5. nginx + HTTPS

Xem [deploy/nginx-foxprofile.conf](../deploy/nginx-foxprofile.conf). Nếu máy đã có nginx phục vụ site khác, chỉ thêm file site mới, chạy `nginx -t` trước khi reload, và không bật firewall khi chưa kiểm tra các dịch vụ đang chạy.

Kiểm tra:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://<domain>/                  # 200
curl -s -o /dev/null -w "%{http_code}\n" https://<domain>/api/v1/profiles   # 401
curl -s -m 5 http://<ip>:8000/ || echo "8000 đóng với Internet (đúng)"
```

## Cập nhật

```bash
runuser -u foxprofile -- git -C /opt/foxprofile/app pull
systemctl restart foxprofile
```

Chạy `git` bằng root trên thư mục của user `foxprofile` sẽ bị từ chối ("dubious ownership"), nên luôn dùng `runuser`.

## Lưu ý về IP của VPS

IP của VPS thuộc dải datacenter. Cloudflare và nhiều trang khác nhận ra điều này, nên dù vân tay sạch và múi giờ khớp IP, Turnstile thường vẫn hiện checkbox thay vì tự qua. Profile chạy trên VPS nên dùng proxy residential hoặc 4G; nút **Kiểm tra IP** trong hộp thoại profile sẽ cảnh báo khi IP bị gắn nhãn datacenter/hosting.
