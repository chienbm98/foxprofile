import hashlib
import io
import json
import tarfile
import zipfile

import pytest

from chrome_engine import fetch, release
from chrome_engine.fetch import FetchError
from chrome_engine.release import Asset, Release


def _zip(path, files):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)


def _tar_xz(path, files):
    with tarfile.open(path, "w:xz") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(data))


def _release(archive, kind, executable, version="1.0.0", sha=None):
    data = archive.read_bytes()
    asset = Asset(
        url=archive.as_uri(),
        sha256=sha or hashlib.sha256(data).hexdigest(),
        size=len(data),
        kind=kind,
        executable=executable,
    )
    return Release(version=version, assets={"test": asset})


@pytest.fixture
def fake_release(monkeypatch):
    registered = {}

    def register(rel):
        registered[rel.version] = rel
        return rel

    monkeypatch.setattr(release, "RELEASES", registered)
    monkeypatch.setattr(
        fetch, "get_release", lambda v=None: registered[v or next(iter(registered))]
    )
    return register


def test_install_zip(tmp_path, fake_release):
    archive = tmp_path / "b.zip"
    _zip(archive, {"chrome-win/chrome.exe": b"MZ", "chrome-win/chrome.dll": b"x"})
    rel = fake_release(_release(archive, "zip", "chrome-win/chrome.exe"))
    home = tmp_path / "home"
    progress = []
    exe = fetch.install(
        rel.version, home=home, host="test", progress=lambda d, t: progress.append((d, t))
    )
    assert exe == home / "1.0.0" / "chrome-win" / "chrome.exe"
    assert exe.read_bytes() == b"MZ"
    assert progress and progress[-1][0] == progress[-1][1]
    marker = json.loads((home / "1.0.0" / fetch.MARKER).read_text())
    assert marker["executable"] == "chrome-win/chrome.exe"
    assert fetch.installed_executable(rel.version, home) == exe
    assert not list(home.glob("*.part"))


def test_install_tar_xz_and_fallback_executable_search(tmp_path, fake_release):
    archive = tmp_path / "b.tar.xz"
    _tar_xz(archive, {"renamed-dir/chrome": b"#!bin", "renamed-dir/lib.so": b"x"})
    rel = fake_release(_release(archive, "tar.xz", "expected-dir/chrome"))
    exe = fetch.install(rel.version, home=tmp_path / "home", host="test")
    assert exe.name == "chrome"
    assert exe.parent.name == "renamed-dir"


def test_install_is_idempotent(tmp_path, fake_release, monkeypatch):
    archive = tmp_path / "b.zip"
    _zip(archive, {"chrome.exe": b"MZ"})
    rel = fake_release(_release(archive, "zip", "chrome.exe"))
    home = tmp_path / "home"
    first = fetch.install(rel.version, home=home, host="test")
    monkeypatch.setattr(fetch, "download", lambda *a, **k: pytest.fail("downloaded twice"))
    assert fetch.install(rel.version, home=home, host="test") == first


def test_checksum_mismatch_leaves_nothing(tmp_path, fake_release):
    archive = tmp_path / "b.zip"
    _zip(archive, {"chrome.exe": b"MZ"})
    rel = fake_release(_release(archive, "zip", "chrome.exe", sha="0" * 64))
    home = tmp_path / "home"
    with pytest.raises(FetchError, match="Checksum mismatch"):
        fetch.install(rel.version, home=home, host="test")
    assert fetch.installed_executable(rel.version, home) is None
    assert list(home.iterdir()) == []


def test_missing_executable_rolls_back(tmp_path, fake_release):
    archive = tmp_path / "b.zip"
    _zip(archive, {"readme.txt": b"no browser here"})
    rel = fake_release(_release(archive, "zip", "chrome.exe"))
    home = tmp_path / "home"
    with pytest.raises(FetchError, match="not found"):
        fetch.install(rel.version, home=home, host="test")
    assert not (home / rel.version).exists()
    assert list(home.iterdir()) == []


def test_path_traversal_is_refused(tmp_path, fake_release):
    archive = tmp_path / "b.zip"
    _zip(archive, {"../evil.exe": b"MZ", "chrome.exe": b"MZ"})
    rel = fake_release(_release(archive, "zip", "chrome.exe"))
    with pytest.raises(FetchError, match="Unsafe path"):
        fetch.install(rel.version, home=tmp_path / "home", host="test")
    assert not (tmp_path / "evil.exe").exists()


def test_download_error_is_wrapped(tmp_path, fake_release):
    missing = tmp_path / "missing.zip"
    asset = Asset(url=missing.as_uri(), sha256="0" * 64, size=1, kind="zip", executable="x")
    fake_release(Release(version="2.0.0", assets={"test": asset}))
    with pytest.raises(FetchError, match="Download failed"):
        fetch.install("2.0.0", home=tmp_path / "home", host="test")


def test_marker_without_executable_is_not_installed(tmp_path, fake_release):
    archive = tmp_path / "b.zip"
    _zip(archive, {"chrome.exe": b"MZ"})
    rel = fake_release(_release(archive, "zip", "chrome.exe"))
    home = tmp_path / "home"
    exe = fetch.install(rel.version, home=home, host="test")
    exe.unlink()
    assert fetch.installed_executable(rel.version, home) is None


def test_uninstall(tmp_path, fake_release):
    archive = tmp_path / "b.zip"
    _zip(archive, {"chrome.exe": b"MZ"})
    rel = fake_release(_release(archive, "zip", "chrome.exe"))
    home = tmp_path / "home"
    fetch.install(rel.version, home=home, host="test")
    assert fetch.uninstall(rel.version, home=home) is True
    assert fetch.uninstall(rel.version, home=home) is False


def test_engine_home_override(monkeypatch, tmp_path):
    monkeypatch.setenv("FOXPROFILE_CHROME_HOME", str(tmp_path))
    assert fetch.engine_home() == tmp_path


@pytest.mark.filterwarnings("ignore:Python 3.14 will:DeprecationWarning")
def test_old_python_extraction_skips_links(tmp_path, fake_release, monkeypatch):
    """Without tarfile filters, symlinks and devices are dropped, not followed."""
    archive = tmp_path / "b.tar.xz"
    with tarfile.open(archive, "w:xz") as tf:
        link = tarfile.TarInfo("dir/escape")
        link.type = tarfile.SYMTYPE
        link.linkname = str(tmp_path / "outside")
        tf.addfile(link)
        info = tarfile.TarInfo("dir/chrome")
        info.size = 2
        tf.addfile(info, io.BytesIO(b"#!"))
    rel = fake_release(_release(archive, "tar.xz", "dir/chrome"))
    monkeypatch.delattr(tarfile, "data_filter", raising=False)
    exe = fetch.install(rel.version, home=tmp_path / "home", host="test")
    assert exe.read_bytes() == b"#!"
    assert not (exe.parent / "escape").exists()
    assert not (exe.parent / "escape").is_symlink()
