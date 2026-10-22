from src.services.browser import browser_cache


def _fake_cache(root, with_marker):
    exe = root / "browsers" / "official" / "156.0.1-beta.36-abc" / "camoufox.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"x")
    if with_marker:
        (root / browser_cache.FLAG).touch()


def test_missing_marker_is_restored_so_camoufox_does_not_wipe_the_browser(tmp_path, monkeypatch):
    monkeypatch.setattr(browser_cache, "cache_dir", lambda: tmp_path)
    _fake_cache(tmp_path, with_marker=False)
    info = browser_cache.status()
    assert info["installed"] and info["marker"] is False
    assert browser_cache.repair_marker() is True
    assert (tmp_path / browser_cache.FLAG).exists()
    assert browser_cache.repair_marker() is False


def test_empty_cache_is_left_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(browser_cache, "cache_dir", lambda: tmp_path)
    assert browser_cache.repair_marker() is False
    assert not (tmp_path / browser_cache.FLAG).exists()
    assert browser_cache.status()["installed"] is False


def test_engine_endpoint_and_start_notes(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from src.api.app import create_app
    from src.core.container import Container

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(browser_cache, "cache_dir", lambda: tmp_path)
    container = Container()
    launcher = container.browser_launcher
    launcher._notes["p"] = "Downloading ---- 0.4/1.3 GB 11.6 MB/s"
    with TestClient(create_app(container), base_url="http://127.0.0.1:8000") as c:
        assert c.get("/api/v1/browser/engine").json()["installed"] is False
        listed = c.get("/api/v1/browser").json()
        assert listed["starting"] == {"p": "Downloading ---- 0.4/1.3 GB 11.6 MB/s"}
