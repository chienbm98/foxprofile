# End-to-end scripts

需要对一个真实的 FoxProfile 手动运行（不属于 `pytest`/CI，因为需要浏览器和网络）。

| 脚本 | 前置条件 | 检查内容 |
| --- | --- | --- |
| `api_e2e.py` | API 已运行 | 固定 fingerprint、cookie JSON/Netscape、launch 成功/失败 |
| `control_e2e.py` | 无（自行运行 launcher，headless） | 页面控制：navigate、snapshot、click、标签页、拦截 `file://` |
| `mcp_stdio_e2e.py` | API 已运行 | 通过 stdio 的 MCP (`python -m src.mcp_server`) |
| `mcp_http_e2e.py` | API 已运行 | `/mcp` 路径的 HTTP MCP，缺少 token 时返回 401 |
| `panel_e2e.py` | API + web panel | 登录、创建/编辑 profile、远程查看屏幕 |
| `mcp_guide_e2e.py` | API + web panel | “Connect AI (MCP)” 对话框 |
| `detection_e2e.py headless headed` | 网络 | 在 bot 检测页面上对比 headless 与有窗口模式 |

环境变量：

```bash
FOXPROFILE_URL=http://127.0.0.1:8000     # FoxProfile 的地址
FOXPROFILE_API_TOKEN=...                 # 如果 server 设置了 token
FOXPROFILE_DATA_DIR=camoufox_data        # api_e2e 在此读取 fingerprint.json
E2E_OUT=e2e-output                       # 截图保存位置
```

这些脚本会创建名为 `e2e-*`、`mcp-demo`、`http-demo`、`panel-demo`、`ctl-test` 的 profile；建议使用单独的数据目录（`FOXPROFILE_DATA_DIR`、`FOXPROFILE_PROFILES_FILE`），不要用真实数据。
