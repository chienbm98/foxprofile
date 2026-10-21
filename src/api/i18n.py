"""Request-scoped language handling and localized API error details."""

from __future__ import annotations

import re
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ..core.strings import current_language, language_context

_LANGUAGE_NAMES = {"en": "en", "vi": "vi", "zh": "zh"}
_ERRORS_ZH: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^Missing or invalid API token$"), "API 令牌缺失或无效"),
    (re.compile(r"^Profile '(.+)' not found$"), "找不到配置“\\1”"),
    (re.compile(r"^Profile already exists$"), "配置已存在"),
    (re.compile(r"^Stop the browser before renaming$"), "重命名前请先停止浏览器"),
    (
        re.compile(r"^A profile's engine cannot be changed; create a new profile instead$"),
        "配置创建后无法更改浏览器内核；请新建配置",
    ),
    (re.compile(r"^Update failed \(name conflict\?\)$"), "更新失败（名称可能已存在）"),
    (re.compile(r"^Stop the browser before deleting$"), "删除前请先停止浏览器"),
    (re.compile(r"^export_dir is not a directory$"), "导出路径不是有效目录"),
    (re.compile(r"^zip_path is not a file$"), "ZIP 路径不是有效文件"),
    (re.compile(r"^Stop the browser before (.+)$"), "操作前请先停止浏览器（\\1）"),
    (re.compile(r"^Profile is busy$"), "配置正在处理中，请稍后重试"),
    (re.compile(r"^Browser already running$"), "浏览器已在运行"),
    (re.compile(r"^Browser is not running$"), "浏览器当前未运行"),
    (re.compile(r"^Browser is still starting$"), "浏览器仍在启动中"),
    (re.compile(r"^Browser did not respond: (.+)$"), "浏览器无响应：\\1"),
    (re.compile(r"^Browser launching for '(.+)'$"), "浏览器正在启动：“\\1”"),
    (re.compile(r"^Browser started for '(.+)'$"), "浏览器已启动：“\\1”"),
    (re.compile(r"^Browser for '(.+)' is still starting$"), "浏览器“\\1”仍在启动中"),
    (re.compile(r"^Launch failed: (.+)$"), "启动失败：\\1"),
    (re.compile(r"^Browser stopped for '(.+)'$"), "浏览器已停止：“\\1”"),
    (re.compile(r"^URL scheme '(.+)' is not allowed$"), "不允许使用 URL 协议“\\1”"),
    (re.compile(r"^Malformed URL: (.+)$"), "URL 格式错误：\\1"),
    (re.compile(r"^No tab at index (\d+)$"), "找不到序号为 \\1 的标签页"),
    (
        re.compile(
            r"^Page is (\d+)px tall; full-page screenshots are limited to "
            r"(\d+)px\. Scroll and take viewport screenshots instead\.$"
        ),
        "页面高度为 \\1px，整页截图上限为 \\2px。请滚动页面并截取视口截图。",
    ),
    (re.compile(r"^Invalid parameters for '(.+)': (.+)$"), "“\\1”的参数无效：\\2"),
    (re.compile(r"^base_url must be an http\(s\) URL$"), "base_url 必须是 http 或 https URL"),
    (re.compile(r"^os_type must be one of: (.+)$"), "os_type 必须是以下值之一：\\1"),
    (re.compile(r"^engine must be one of: (.+)$"), "engine 必须是以下值之一：\\1"),
    (re.compile(r"^Chrome engine unavailable here: (.+)$"), "此设备无法使用 Chrome 内核：\\1"),
    (re.compile(r"^Malformed URL: no host$"), "URL 格式错误：缺少主机名"),
    (
        re.compile(r"^Only about:blank is allowed among about: pages$"),
        "about: 页面仅允许 about:blank",
    ),
    (
        re.compile(r"^Cannot close the last tab; stop the profile instead$"),
        "无法关闭最后一个标签页；请停止该配置",
    ),
    (re.compile(r"^Unknown action '(.+)'$"), "未知操作：“\\1”"),
    (re.compile(r"^Invalid proxy format$"), "代理格式无效"),
    (re.compile(r"^Proxy returned status (\d+)$"), "代理服务器返回状态码 \\1"),
    (re.compile(r"^Proxy connection timed out$"), "代理连接超时"),
    (re.compile(r"^Failed to connect to proxy$"), "连接代理服务器失败"),
    (re.compile(r"^Proxy error: (.+)$"), "代理错误：\\1"),
    (re.compile(r"^Error checking proxy: (.+)$"), "检查代理时出错：\\1"),
)

_VALIDATION_ZH = {
    "missing": "此字段为必填项",
    "string_type": "请输入文本",
    "string_too_short": "输入内容过短",
    "string_too_long": "输入内容过长",
    "int_parsing": "请输入有效整数",
    "float_parsing": "请输入有效数字",
    "bool_parsing": "请输入有效布尔值",
    "string_pattern_mismatch": "输入格式不符合要求",
    "greater_than_equal": "数值不能小于 {ge}",
    "less_than_equal": "数值不能大于 {le}",
    "literal_error": "输入值不在允许范围内",
    "enum": "输入值不在允许范围内",
    "json_invalid": "JSON 格式无效",
}


def requested_language(header: str) -> str | None:
    """Select the best supported language from an Accept-Language header."""
    candidates: list[tuple[float, int, str]] = []
    for index, item in enumerate(header.split(",")):
        parts = item.strip().split(";")
        language = parts[0].strip().lower().replace("_", "-")
        quality = 1.0
        for parameter in parts[1:]:
            key, separator, value = parameter.strip().partition("=")
            if separator and key.strip().lower() == "q":
                try:
                    quality = float(value)
                except ValueError:
                    quality = 0.0
        if quality <= 0:
            continue
        code = language.split("-", 1)[0]
        if code in _LANGUAGE_NAMES:
            candidates.append((quality, -index, _LANGUAGE_NAMES[code]))
    return max(candidates)[2] if candidates else None


class LanguageMiddleware:
    """Expose Accept-Language to translation helpers for the whole request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", ()))
        language = requested_language(headers.get(b"accept-language", b"").decode("latin-1"))
        if language is None:
            await self.app(scope, receive, send)
            return
        with language_context(language):
            await self.app(scope, receive, send)


def localize_detail(detail: Any) -> Any:
    if current_language() != "zh" or not isinstance(detail, str):
        return detail
    for pattern, translated in _ERRORS_ZH:
        if pattern.match(detail):
            return pattern.sub(translated, detail)
    return detail


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    from fastapi import HTTPException

    assert isinstance(exc, HTTPException)
    return JSONResponse(
        jsonable_encoder({"detail": localize_detail(exc.detail)}),
        status_code=exc.status_code,
        headers=exc.headers,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = exc.errors()
    if current_language() == "zh":
        for error in errors:
            message = _VALIDATION_ZH.get(error.get("type", ""))
            if message:
                context = error.get("ctx", {})
                error["msg"] = message.format(**context)
    return JSONResponse(jsonable_encoder({"detail": errors}), status_code=422)
