"""Storage backends for synced profiles: a folder, WebDAV, or S3-compatible."""

from __future__ import annotations

import base64
import os
import pathlib
import shutil
import urllib.error
import urllib.parse
import urllib.request
from typing import Protocol


class SyncError(Exception):
    pass


class Backend(Protocol):
    def upload(self, key: str, path: str) -> None: ...
    def download(self, key: str, path: str) -> None: ...
    def read(self, key: str) -> bytes | None: ...
    def write(self, key: str, data: bytes) -> None: ...
    def delete(self, key: str) -> None: ...
    def list(self) -> list[str]: ...


class FolderBackend:
    """Any directory: a network share, Syncthing/Dropbox folder, mounted bucket."""

    def __init__(self, root: str) -> None:
        self.root = pathlib.Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _p(self, key: str) -> pathlib.Path:
        return self.root / key

    def upload(self, key: str, path: str) -> None:
        tmp = self._p(key + ".part")
        shutil.copyfile(path, tmp)
        os.replace(tmp, self._p(key))

    def download(self, key: str, path: str) -> None:
        shutil.copyfile(self._p(key), path)

    def read(self, key: str) -> bytes | None:
        p = self._p(key)
        return p.read_bytes() if p.exists() else None

    def write(self, key: str, data: bytes) -> None:
        tmp = self._p(key + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, self._p(key))

    def delete(self, key: str) -> None:
        self._p(key).unlink(missing_ok=True)

    def list(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir() if p.is_file())


class WebDAVBackend:
    def __init__(self, url: str, user: str = "", password: str = "") -> None:
        self.base = url.rstrip("/") + "/"
        self.auth = (
            "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode() if user else ""
        )
        self._request("MKCOL", "", ok=(201, 301, 405))

    def _request(self, method, key, data=None, ok=(200, 201, 204), headers=None, stream=None):
        req = urllib.request.Request(
            self.base + urllib.parse.quote(key), data=data, method=method, headers=headers or {}
        )
        if self.auth:
            req.add_header("Authorization", self.auth)
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                if stream is not None:
                    shutil.copyfileobj(r, stream)
                    return b""
                body = r.read()
                if r.status not in ok and not (200 <= r.status < 300):
                    raise SyncError(f"WebDAV {method} {key}: HTTP {r.status}")
                return body
        except urllib.error.HTTPError as e:
            if e.code in ok:
                return b""
            if e.code == 404:
                return None
            raise SyncError(f"WebDAV {method} {key}: HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise SyncError(f"WebDAV unreachable: {e.reason}") from e

    def upload(self, key: str, path: str) -> None:
        with open(path, "rb") as f:
            self._request(
                "PUT", key, data=f, headers={"Content-Length": str(os.path.getsize(path))}
            )

    def download(self, key: str, path: str) -> None:
        with open(path, "wb") as f:
            if self._request("GET", key, stream=f) is None:
                raise SyncError(f"{key} not found on the server")

    def read(self, key: str) -> bytes | None:
        return self._request("GET", key)

    def write(self, key: str, data: bytes) -> None:
        self._request("PUT", key, data=data)

    def delete(self, key: str) -> None:
        self._request("DELETE", key)

    def list(self) -> list[str]:
        body = self._request("PROPFIND", "", headers={"Depth": "1"}, ok=(207,))
        if not body:
            return []
        import re

        hrefs = re.findall(rb"<[^>]*href[^>]*>([^<]+)<", body, flags=re.I)
        names = {urllib.parse.unquote(h.decode()).rstrip("/").rsplit("/", 1)[-1] for h in hrefs}
        base = urllib.parse.urlparse(self.base).path.rstrip("/").rsplit("/", 1)[-1]
        return sorted(n for n in names if n and n != base)


class S3Backend:
    """S3 or compatible (R2, MinIO, B2). Needs `pip install boto3`."""

    def __init__(self, bucket: str, prefix: str = "", endpoint: str | None = None) -> None:
        try:
            import boto3
        except ImportError as e:
            raise SyncError("S3 sync needs boto3: pip install boto3") from e
        self.s3 = boto3.client("s3", endpoint_url=endpoint)
        self.bucket = bucket
        self.prefix = prefix.strip("/") + "/" if prefix.strip("/") else ""

    def _k(self, key: str) -> str:
        return self.prefix + key

    def upload(self, key: str, path: str) -> None:
        self.s3.upload_file(path, self.bucket, self._k(key))

    def download(self, key: str, path: str) -> None:
        self.s3.download_file(self.bucket, self._k(key), path)

    def read(self, key: str) -> bytes | None:
        try:
            return self.s3.get_object(Bucket=self.bucket, Key=self._k(key))["Body"].read()
        except self.s3.exceptions.NoSuchKey:
            return None

    def write(self, key: str, data: bytes) -> None:
        self.s3.put_object(Bucket=self.bucket, Key=self._k(key), Body=data)

    def delete(self, key: str) -> None:
        self.s3.delete_object(Bucket=self.bucket, Key=self._k(key))

    def list(self) -> list[str]:
        out: list[str] = []
        pages = self.s3.get_paginator("list_objects_v2").paginate(
            Bucket=self.bucket, Prefix=self.prefix
        )
        for page in pages:
            out += [o["Key"][len(self.prefix) :] for o in page.get("Contents", [])]
        return sorted(out)


def open_backend(url: str, env: dict[str, str] | None = None) -> Backend:
    """`folder:/path`, a plain path, `webdav(s)://host/path`, or `s3://bucket/prefix`."""
    env = env if env is not None else dict(os.environ)
    if not url:
        raise SyncError("Sync is not configured: set FOXPROFILE_SYNC_URL")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in ("webdav", "webdavs"):
        real = (
            ("https" if parsed.scheme == "webdavs" else "http")
            + "://"
            + parsed.netloc.split("@")[-1]
            + parsed.path
        )
        return WebDAVBackend(
            real,
            urllib.parse.unquote(parsed.username or env.get("FOXPROFILE_SYNC_USER", "")),
            urllib.parse.unquote(parsed.password or env.get("FOXPROFILE_SYNC_PASSWORD", "")),
        )
    if parsed.scheme == "s3":
        return S3Backend(parsed.netloc, parsed.path, env.get("FOXPROFILE_SYNC_S3_ENDPOINT"))
    if len(parsed.scheme) > 1 and parsed.scheme != "folder":
        raise SyncError(f"Unsupported sync URL scheme: {parsed.scheme}")
    return FolderBackend(url.removeprefix("folder:"))
