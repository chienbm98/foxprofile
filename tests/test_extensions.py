"""Extension cache: vendor archives, extraction and per-profile install."""

import base64
import hashlib
import io
import json
import zipfile

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from src.services.browser import extensions

FIREFOX_ID = "vpn@proton.ch"
CHROMIUM_ID = "jplgfhpmjnbigmhklmmbgecoobifkmpa"


def _xpi(version="1.3.7") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "manifest_version": 3,
                    "version": version,
                    "name": "Proton VPN",
                    "browser_specific_settings": {"gecko": {"id": FIREFOX_ID}},
                }
            ),
        )
        archive.writestr("background.js", "// extension")
    return buffer.getvalue()


def _varint_bytes(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if not value:
            return bytes(out + bytes([byte]))
        out.append(byte | 0x80)


def _field(number: int, value: bytes) -> bytes:
    """One length-delimited protobuf field, as CRX headers use them."""
    return _varint_bytes((number << 3) | 2) + _varint_bytes(len(value)) + value


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _signed_crx3(payload: bytes, key) -> tuple[bytes, str]:
    """A CRX3 signed the way Chrome signs one. Returns (file bytes, extension id)."""
    der = key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    signed_header = _field(1, hashlib.sha256(der).digest()[:16])  # SignedData { crx_id }
    message = (
        b"CRX3 SignedData\x00" + len(signed_header).to_bytes(4, "little") + signed_header + payload
    )
    proof = _field(1, der) + _field(2, key.sign(message, padding.PKCS1v15(), hashes.SHA256()))
    header = _field(2, proof) + _field(10000, signed_header)
    crx = b"Cr24" + (3).to_bytes(4, "little") + len(header).to_bytes(4, "little") + header + payload
    return crx, extensions.chromium_id(base64.b64encode(der).decode())


def _zip(*files: tuple[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files:
            archive.writestr(name, content)
    return buffer.getvalue()


@pytest.fixture
def home(tmp_path, monkeypatch):
    path = tmp_path / "extensions-cache"
    monkeypatch.setenv("FOXPROFILE_EXTENSIONS_HOME", str(path))
    return path


def _cache_firefox(home, version="1.3.7") -> None:
    directory = home / "proton-vpn" / "firefox"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "proton-vpn.xpi").write_bytes(_xpi(version))
    (directory / "meta.json").write_text(json.dumps({"version": version}), encoding="utf-8")


def _cache_chromium(home, version="1.3.7") -> None:
    directory = home / "proton-vpn" / "chromium"
    unpacked = directory / "unpacked"
    unpacked.mkdir(parents=True, exist_ok=True)
    (unpacked / "manifest.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    (directory / "meta.json").write_text(json.dumps({"version": version}), encoding="utf-8")


# --- vendor archives -------------------------------------------------------------------


def test_a_signed_crx3_verifies_and_yields_its_zip(signing_key):
    payload = _zip(("manifest.json", '{"version": "1.0"}'))
    crx, extension_id = _signed_crx3(payload, signing_key)
    assert extensions._verify_crx3(crx, extension_id) == payload


def test_a_tampered_archive_is_rejected(signing_key):
    crx, extension_id = _signed_crx3(_zip(("manifest.json", "{}")), signing_key)
    tampered = crx[:-1] + bytes([crx[-1] ^ 0x01])
    with pytest.raises(extensions.ExtensionError, match="does not verify"):
        extensions._verify_crx3(tampered, extension_id)


def test_a_crx_signed_by_another_key_is_rejected(signing_key):
    crx, _ = _signed_crx3(_zip(("manifest.json", "{}")), signing_key)
    with pytest.raises(extensions.ExtensionError, match="not signed by"):
        extensions._verify_crx3(crx, "jmkgmabhbidmpfdgeejhckdkijjhghgo")


def test_an_unsigned_crx3_is_rejected():
    payload = _zip(("manifest.json", "{}"))
    crx = b"Cr24" + (3).to_bytes(4, "little") + (0).to_bytes(4, "little") + payload
    with pytest.raises(extensions.ExtensionError, match="no signed data"):
        extensions._verify_crx3(crx, CHROMIUM_ID)


def test_the_legacy_crx2_format_is_rejected():
    crx = b"Cr24" + (2).to_bytes(4, "little") + b"\x00" * 8 + _zip(("manifest.json", "{}"))
    with pytest.raises(extensions.ExtensionError, match="Unsupported CRX version"):
        extensions._verify_crx3(crx, CHROMIUM_ID)


def test_zip_manifest_and_extract(tmp_path):
    payload = _zip(("manifest.json", '{"version": "2.0"}'), ("js/app.js", "// code"))
    assert extensions._manifest(payload) == {"version": "2.0"}
    extensions._extract(payload, tmp_path)
    assert json.loads((tmp_path / "manifest.json").read_text()) == {"version": "2.0"}
    assert (tmp_path / "js" / "app.js").read_text() == "// code"


def test_zip_without_manifest_is_rejected():
    with pytest.raises(extensions.ExtensionError):
        extensions._manifest(_zip(("other.txt", "x")))


def test_chromium_id_matches_the_extension_id_algorithm():
    # Same derivation as Chrome: SHA-256 of the DER key, first 16 bytes, each
    # nibble mapped to a-p.
    assert extensions.chromium_id("Zm94cHJvZmlsZS10ZXN0LWtleQ==") == (
        "jmkgmabhbidmpfdgeejhckdkijjhghgo"
    )


def test_zip_cannot_escape_the_target(tmp_path):
    with pytest.raises(extensions.ExtensionError):
        extensions._extract(_zip(("../evil.txt", "x")), tmp_path / "unpacked")


# --- Camoufox --------------------------------------------------------------------------


def test_firefox_addon_lands_in_the_profile(home, tmp_path):
    _cache_firefox(home)
    profile = tmp_path / "profile"

    assert extensions.install_firefox(profile, names=("proton-vpn",)) == ["Proton VPN 1.3.7"]
    installed = profile / "extensions" / f"{FIREFOX_ID}.xpi"
    assert installed.is_file()
    assert installed.read_bytes() == _xpi()


def test_firefox_addon_is_not_rewritten_when_unchanged(home, tmp_path):
    _cache_firefox(home)
    profile = tmp_path / "profile"
    extensions.install_firefox(profile, names=("proton-vpn",))
    installed = profile / "extensions" / f"{FIREFOX_ID}.xpi"
    first = installed.stat().st_mtime_ns
    extensions.install_firefox(profile, names=("proton-vpn",))
    assert installed.stat().st_mtime_ns == first
    assert installed.read_bytes() == _xpi()
    assert list((profile / "extensions").glob("*.part")) == []


def test_a_new_cached_build_replaces_the_profile_copy(home, tmp_path):
    _cache_firefox(home)
    profile = tmp_path / "profile"
    extensions.install_firefox(profile, names=("proton-vpn",))
    installed = profile / "extensions" / f"{FIREFOX_ID}.xpi"
    assert installed.read_bytes() == _xpi("1.3.7")

    _cache_firefox(home, "1.3.8")  # same byte length, different build
    assert extensions.install_firefox(profile, names=("proton-vpn",)) == ["Proton VPN 1.3.8"]
    assert installed.read_bytes() == _xpi("1.3.8")


def test_no_extension_touches_nothing(home, tmp_path):
    profile = tmp_path / "profile"
    assert extensions.install_firefox(profile, names=()) == []
    assert not (profile / "extensions").exists()


def test_unselecting_the_extension_removes_the_profile_copy(home, tmp_path):
    _cache_firefox(home)
    profile = tmp_path / "profile"
    extensions.install_firefox(profile, names=("proton-vpn",))

    assert extensions.remove_firefox(profile) == ["proton-vpn"]
    assert not (profile / "extensions" / f"{FIREFOX_ID}.xpi").exists()
    assert not (profile / ".foxprofile-extensions.json").exists()
    assert extensions.remove_firefox(profile) == []


def test_removal_leaves_addons_the_user_installed(home, tmp_path):
    profile = tmp_path / "profile"
    user_addon = profile / "extensions" / "user@example.xpi"
    user_addon.parent.mkdir(parents=True)
    user_addon.write_bytes(b"user addon")

    assert extensions.remove_firefox(profile) == []
    assert user_addon.is_file()


# --- Chrome ----------------------------------------------------------------------------


def test_chromium_load_extension_arg(home):
    _cache_chromium(home)
    args = extensions.chromium_extra_args(names=("proton-vpn",))
    assert args == [f"--load-extension={home / 'proton-vpn' / 'chromium' / 'unpacked'}"]


def test_chromium_args_are_empty_without_configuration(home):
    assert extensions.chromium_extra_args(names=()) == []


def test_refresh_replaces_the_cached_builds(home, monkeypatch):
    _cache_firefox(home)
    _cache_chromium(home)
    fetched = []

    def fake_firefox(extension, cache):
        fetched.append(("firefox", cache))
        return cache / "proton-vpn" / "firefox" / "proton-vpn.xpi"

    def fake_chromium(extension, cache):
        fetched.append(("chromium", cache))
        return cache / "proton-vpn" / "chromium" / "unpacked"

    monkeypatch.setattr(extensions, "_store_firefox", fake_firefox)
    monkeypatch.setattr(extensions, "_store_chromium", fake_chromium)

    assert extensions.refresh(names=("proton-vpn",)) == ["Proton VPN"]
    assert [engine for engine, _ in fetched] == ["firefox", "chromium"]
    assert fetched[0][1] == home
