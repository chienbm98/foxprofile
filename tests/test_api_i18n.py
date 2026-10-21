import asyncio

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.container import Container
from src.core.strings import current_language, get_string, language_context


def test_accept_language_selects_supported_locale_by_quality():
    from src.api.i18n import requested_language

    assert requested_language("zh-CN, en;q=0.8") == "zh"
    assert requested_language("zh;q=0.2, en;q=0.9") == "en"
    assert requested_language("fr-FR, vi-VN;q=0.7") == "vi"
    assert requested_language("fr-FR") is None


def test_language_context_is_isolated_between_concurrent_tasks():
    async def translated(code):
        with language_context(code):
            await asyncio.sleep(0)
            return current_language(), get_string("validation_empty_name")

    async def run_both():
        return await asyncio.gather(translated("zh"), translated("vi"))

    results = asyncio.run(run_both())
    assert results[0] == ("zh", "配置名称不能为空")
    assert results[1][0] == "vi"


def test_browser_and_proxy_errors_are_localized():
    from src.api.i18n import localize_detail

    with language_context("zh"):
        assert localize_detail("No tab at index 2") == "找不到序号为 2 的标签页"
        assert localize_detail("Proxy returned status 407") == "代理服务器返回状态码 407"
        assert localize_detail("URL scheme 'file' is not allowed") == "不允许使用 URL 协议“file”"


def test_api_errors_follow_accept_language(monkeypatch, tmp_path):
    from src.api import auth
    from src.services.profile import manager

    monkeypatch.setattr(auth, "API_TOKEN", "")
    monkeypatch.setattr(manager, "PROFILES_FILE", str(tmp_path / "profiles.json"))
    monkeypatch.setattr(manager, "DATA_DIR", str(tmp_path / "profiles"))
    client = TestClient(create_app(Container()), base_url="http://127.0.0.1")

    zh = client.post(
        "/api/v1/profiles",
        headers={"Accept-Language": "zh-CN"},
        json={"name": "sample", "proxy": "not-a-proxy"},
    )
    assert zh.status_code == 400
    assert zh.json()["detail"].startswith("Proxy 格式无效")

    translated_server_error = client.post(
        "/api/v1/profiles",
        headers={"Accept-Language": "zh"},
        json={"name": "sample", "os_type": "other"},
    )
    assert (
        translated_server_error.json()["detail"]
        == "os_type 必须是以下值之一：windows, macos, linux"
    )

    missing_field = client.post("/api/v1/profiles", headers={"Accept-Language": "zh"}, json={})
    assert missing_field.status_code == 422
    assert missing_field.json()["detail"][0]["msg"] == "此字段为必填项"

    invalid_format = client.get(
        "/api/v1/profiles/missing/cookies?format=xml", headers={"Accept-Language": "zh"}
    )
    assert invalid_format.status_code == 422
    assert invalid_format.json()["detail"][0]["msg"] == "输入格式不符合要求"

    english = client.get("/api/v1/profiles/missing", headers={"Accept-Language": "en"})
    assert english.status_code == 404
    assert english.json()["detail"] == "Profile 'missing' not found"

    chinese = client.get("/api/v1/profiles/missing", headers={"Accept-Language": "zh"})
    assert chinese.status_code == 404
    assert chinese.json()["detail"] == "找不到配置“missing”"
