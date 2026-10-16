# 为 FoxProfile 做贡献

感谢你愿意参与贡献！我们欢迎各种形式的贡献：报告 bug、提出功能建议、修正文档、翻译或编写代码。

*English speakers: issues and pull requests in English are welcome too.*

## 报告问题与提出建议

- **Bug：** 按“Bug 报告”模板[新建 issue](../../issues/new/choose)。请写明操作系统、Python 版本、复现步骤，并附上 `logs/` 中的日志片段。
- **功能：** 使用“功能建议”模板。较大的改动建议先开 issue 讨论再动手写代码，避免做完后不被接受。
- **安全漏洞：** 请不要公开提交 issue。见 [SECURITY.md](SECURITY.md)。

> ⚠️ 附上日志或文件之前，请先删除 cookie、带密码的 proxy 以及所有账号信息。

## 提交 Pull Request 的流程

1. **Fork** 本仓库到你的账号，然后 clone 到本地。
2. 从 `main` **创建分支**，按改动类型命名：
   - `feat/<描述>`：新功能
   - `fix/<描述>`：修复 bug
   - `docs/<描述>`：文档
   - `refactor/<描述>`、`test/<描述>`、`chore/<描述>`
3. **搭建开发环境：**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # Windows
   source .venv/bin/activate       # Linux/macOS
   pip install -r requirements-dev.txt
   python -m camoufox fetch        # 仅在想运行应用时才需要
   ```
4. **编写代码和测试。** 修复 bug 时添加能复现该 bug 的测试；新增功能时为逻辑部分添加测试。
5. **推送前检查：**
   ```bash
   ruff check src tests
   ruff format --check src tests
   pytest
   ```
6. 按 [Conventional Commits](https://www.conventionalcommits.org/) 规范**提交 commit**：
   ```text
   feat(cookies): export cookies as Netscape cookies.txt
   fix(api): report failed launches with status 502
   docs: add proxy format examples
   ```
7. 向 `main` 分支**发起 Pull Request**，并完整填写 PR 模板。CI 会在 Windows、Linux 和 macOS 上自动运行 lint 和测试。只有 CI 通过并且至少有一位 maintainer 批准后，PR 才会被合并。

## 代码规范

- Python ≥ 3.10，新函数需要类型标注。
- 使用 `ruff` 格式化和 lint（配置在 `pyproject.toml` 中）。
- **界面上显示的文字不要硬编码**，而是添加到 `src/core/strings.py` 中的 `en` **和** `zh-CN` 两种语言里，再调用 `get_string("key")`。任意一种语言缺少 key，测试都会报错。
- 在把 profile 名称用作路径之前，必须先经过 `validate_profile_name`。
- 不要提交 `profiles.json`、`camoufox_data/`、`logs/` 或 `.env` 文件：它们包含真实的 cookie 和 proxy。

## 目录结构

```text
src/
  api/          REST API (FastAPI): routes, schemas, token auth, /mcp over HTTP
  mcp_server/   MCP tools (client of the REST API; stdio entry: foxprofile_mcp.py)
  web/          web panel (one HTML file, no build step)
  server.py     server mode entry point (API + panel, no desktop UI)
  core/         配置、日志、多语言文案
  models/       Profile dataclass
  services/
    browser/    启动 Camoufox、fingerprint、cookie、页面控制 (control.py)
    profile/    保存、导出/导入 profile
    proxy/      proxy 检测、Check IP (GeoIP 对比)
  ui/           Flet 界面：components、dialogs、actions
  utils/        名称校验、proxy 解析
tests/          pytest
```

## 许可证

提交贡献即表示你同意该贡献按项目的 [MIT 许可证](LICENSE)发布。

所有参与者都需要遵守[行为准则](CODE_OF_CONDUCT.md)。
