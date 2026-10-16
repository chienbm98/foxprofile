# 安全政策

## 报告漏洞

**请勿为安全漏洞公开提交 issue。** 请通过本仓库的 **Security → Report a vulnerability** 选项卡私下报告（GitHub Private Vulnerability Reporting）。

请尽量写明：

- 漏洞描述及其影响
- 复现步骤
- 受影响的版本或 commit

Maintainer 会在 7 天内回复，并在公开细节之前先发布修复版本。

## 重点关注范围

FoxProfile 保存着多个账号的登录 cookie 和 proxy，因此以下问题的优先级最高：

- 读取或写入数据目录之外的文件（通过 profile 名称或导入的 ZIP 文件进行 path traversal）
- cookie、proxy 或 proxy 密码泄露到日志中或本机之外
- 在用户没有主动配置的情况下，让 REST API 监听 `127.0.0.1` 以外的地址
- 绕过 API / web panel 的 token，或不带 token 访问浏览器控制通道 (`control.py`)
- 让 AI agent 通过 MCP 打开 `file://` URL 或读取本机文件

## 给用户的提醒

- 暴露到公网时，务必设置 `FOXPROFILE_API_TOKEN`（至少 24 个随机字符）并使用 HTTPS。
- 网页内容属于不可信数据：网页中可能包含用来欺骗 AI agent 的指令。
- `camoufox_data/` 目录保存着登录 cookie。不要分享，也不要提交。
- 只导入你信任来源的 profile ZIP 或 cookie 文件。
