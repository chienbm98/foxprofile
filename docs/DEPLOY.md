# 将 FoxProfile 部署到 VPS（Ubuntu 24.04）

以 server 模式运行 FoxProfile（API、web panel、MCP），置于启用 HTTPS 的 nginx 之后，并使用独立的系统用户。8000 端口只监听 `127.0.0.1`；所有外部访问都经过 nginx，并且需要 API token。

## 1. 系统软件包与独立用户

```bash
apt-get update
apt-get install -y git python3-venv xvfb libgtk-3-0t64 libx11-xcb1 libasound2t64 \
  libdbus-glib-1-2 certbot python3-certbot-nginx
useradd --system --create-home --home-dir /opt/foxprofile --shell /usr/sbin/nologin foxprofile
```

Ubuntu 22.04：使用 `libgtk-3-0` 和 `libasound2`（没有 `t64` 后缀）。

## 2. 代码、依赖库、浏览器

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

## 4. Service

```bash
cp deploy/foxprofile.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now foxprofile
curl -s http://127.0.0.1:8000/api/v1/info    # "headless":"virtual", "auth_required":true
```

## 5. nginx + HTTPS

参见 [deploy/nginx-foxprofile.conf](../deploy/nginx-foxprofile.conf)。如果机器上已有 nginx 在为其他站点提供服务，只需新增一个站点文件，reload 之前先运行 `nginx -t`，并且在检查现有运行的服务之前不要启用防火墙。

验证：

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://<domain>/                  # 200
curl -s -o /dev/null -w "%{http_code}\n" https://<domain>/api/v1/profiles   # 401
curl -s -m 5 http://<ip>:8000/ || echo "8000 端口对 Internet 关闭（正确）"
```

## 更新

```bash
runuser -u foxprofile -- git -C /opt/foxprofile/app pull
systemctl restart foxprofile
```

以 root 身份在 `foxprofile` 用户的目录里运行 `git` 会被拒绝（"dubious ownership"），所以请始终使用 `runuser`。

## 关于 VPS 的 IP

VPS 的 IP 属于机房（datacenter）网段。Cloudflare 和许多其他网站都能识别出这一点，所以即使 fingerprint 干净、timezone 也与 IP 一致，Turnstile 通常仍会弹出复选框，而不是自动通过。在 VPS 上运行的 profile 应该使用 residential 或 4G proxy；profile 对话框中的 **Check IP** 按钮会在 IP 被标记为 datacenter/hosting 时给出警告。
