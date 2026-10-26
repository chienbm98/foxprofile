# 在 VPS（Ubuntu 24.04）上部署 FoxProfile

以服务器模式运行 FoxProfile（API、Web 面板、MCP），通过 nginx 提供 HTTPS，并使用独立的系统用户。8000 端口仅监听 `127.0.0.1`；所有外部访问都经由 nginx，并需要 API 令牌。

## 1. 系统软件包与专用用户

```bash
apt-get update
apt-get install -y git python3-venv xvfb libgtk-3-0t64 libx11-xcb1 libasound2t64 \
  libdbus-glib-1-2 certbot python3-certbot-nginx
useradd --system --create-home --home-dir /opt/foxprofile --shell /usr/sbin/nologin foxprofile
```

Ubuntu 22.04：使用 `libgtk-3-0` 和 `libasound2`（不带 `t64` 后缀）。

## 2. 获取代码、安装依赖和浏览器

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

## 3. 配置

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
echo "Token: $TOKEN"   # 保存到密码管理器
```

## 4. 服务

```bash
cp deploy/foxprofile.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now foxprofile
curl -s http://127.0.0.1:8000/api/v1/info    # "headless":"virtual", "auth_required":true
```

## 5. nginx + HTTPS

请参阅 [deploy/nginx-foxprofile.conf](../deploy/nginx-foxprofile.conf)。如果服务器上已有 nginx 为其他站点提供服务，只需添加新的站点配置文件；重新加载前先运行 `nginx -t`，并在确认当前运行的服务之前不要启用防火墙。

验证：

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://<domain>/                  # 200
curl -s -o /dev/null -w "%{http_code}\n" https://<domain>/api/v1/profiles   # 401
curl -s -m 5 http://<ip>:8000/ || echo "8000 对 Internet 关闭（正确）"
```

## 更新

```bash
runuser -u foxprofile -- git -C /opt/foxprofile/app pull
systemctl restart foxprofile
```

以 root 身份在 `foxprofile` 用户的目录中运行 `git` 会因“dubious ownership”（所有权不可信）而被拒绝，因此始终使用 `runuser`。

## 关于 VPS IP 的说明

VPS 的 IP 属于数据中心地址段。Cloudflare 和许多其他网站都能识别这一点，因此即使浏览器指纹干净且时区与 IP 匹配，Turnstile 通常仍会显示复选框，而不是自动通过。部署在 VPS 上的配置建议使用住宅或 4G 代理；配置对话框中的 **检查 IP** 按钮会在 IP 被标记为数据中心/托管服务时发出提示。
