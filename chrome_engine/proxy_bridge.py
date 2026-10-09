"""A loopback proxy that lets Chromium use proxies with credentials.

Chromium cannot take proxy credentials on the command line, and it cannot
authenticate to SOCKS5 proxies at all. The bridge listens on 127.0.0.1 without
authentication, Chromium is pointed at it as a plain HTTP proxy, and the bridge
opens every connection through the real upstream proxy with its credentials.

Target hostnames are always passed to the upstream (HTTP CONNECT or SOCKS5
domain addressing), never resolved here, so DNS does not leak past the proxy.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import ipaddress
import ssl
from collections import deque
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

_HEAD_LIMIT = 64 * 1024
_BUFFER = 64 * 1024
CONNECT_TIMEOUT = 20.0
_HOP_HEADERS = {"proxy-authorization", "proxy-connection", "connection", "keep-alive"}


class UpstreamError(Exception):
    """The upstream proxy refused or failed a connection."""


@dataclass(frozen=True)
class Upstream:
    scheme: str  # http, https, socks5
    host: str
    port: int
    username: str | None = None
    password: str | None = None

    @classmethod
    def parse(cls, proxy: str) -> Upstream:
        """Parse scheme://user:pass@host:port or host:port:user:pass (http by default)."""
        from src.utils.proxy_parser import normalize_proxy

        text = normalize_proxy(proxy.strip())
        if "://" not in text:
            text = "http://" + text
        parts = urlsplit(text)
        scheme = parts.scheme.lower()
        if scheme == "socks5h":
            scheme = "socks5"
        if scheme not in ("http", "https", "socks5"):
            raise ValueError(f"Unsupported proxy scheme {parts.scheme!r} (http, https, socks5)")
        try:
            port = parts.port
        except ValueError:
            port = None
        if not parts.hostname or not port:
            raise ValueError("Proxy must include a host and a port")
        return cls(
            scheme=scheme,
            host=parts.hostname,
            port=port,
            username=unquote(parts.username) if parts.username else None,
            password=unquote(parts.password) if parts.password else None,
        )

    @property
    def display(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"

    def basic_auth(self) -> str | None:
        if not self.username:
            return None
        raw = f"{self.username}:{self.password or ''}".encode()
        return "Basic " + base64.b64encode(raw).decode()


async def _read_head(reader: asyncio.StreamReader) -> bytes:
    try:
        return await reader.readuntil(b"\r\n\r\n")
    except asyncio.LimitOverrunError as e:
        raise UpstreamError("Header too large") from e


def _split_host_port(authority: str, default_port: int) -> tuple[str, int]:
    if authority.startswith("["):
        host, _, rest = authority[1:].partition("]")
        port = rest[1:] if rest.startswith(":") else ""
    else:
        host, _, port = authority.rpartition(":") if ":" in authority else (authority, "", "")
    return host, int(port) if port else default_port


async def open_tunnel(
    upstream: Upstream, host: str, port: int
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """A byte stream to host:port through the upstream proxy."""
    use_tls = ssl.create_default_context() if upstream.scheme == "https" else None
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(
            upstream.host,
            upstream.port,
            ssl=use_tls,
            server_hostname=upstream.host if use_tls else None,
            limit=_HEAD_LIMIT,
        ),
        CONNECT_TIMEOUT,
    )
    try:
        if upstream.scheme == "socks5":
            await asyncio.wait_for(
                _socks5_connect(reader, writer, upstream, host, port), CONNECT_TIMEOUT
            )
        else:
            await asyncio.wait_for(
                _http_connect(reader, writer, upstream, host, port), CONNECT_TIMEOUT
            )
    except BaseException:
        writer.close()
        raise
    return reader, writer


def _authority(host: str, port: int) -> str:
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


async def _http_connect(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    upstream: Upstream,
    host: str,
    port: int,
) -> None:
    target = _authority(host, port)
    lines = [f"CONNECT {target} HTTP/1.1", f"Host: {target}"]
    auth = upstream.basic_auth()
    if auth:
        lines.append(f"Proxy-Authorization: {auth}")
    writer.write(("\r\n".join(lines) + "\r\n\r\n").encode())
    await writer.drain()
    head = await _read_head(reader)
    status = head.split(b"\r\n", 1)[0].decode("latin-1")
    parts = status.split(" ", 2)
    if len(parts) < 2 or parts[1] != "200":
        raise UpstreamError(f"Upstream refused CONNECT {target}: {status}")


_SOCKS_REPLIES = {
    1: "general failure",
    2: "connection not allowed",
    3: "network unreachable",
    4: "host unreachable",
    5: "connection refused",
    6: "TTL expired",
    7: "command not supported",
    8: "address type not supported",
}


async def _socks5_connect(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    upstream: Upstream,
    host: str,
    port: int,
) -> None:
    methods = b"\x00\x02" if upstream.username else b"\x00"
    writer.write(b"\x05" + bytes([len(methods)]) + methods)
    await writer.drain()
    version, method = await reader.readexactly(2)
    if version != 5:
        raise UpstreamError("Upstream is not a SOCKS5 proxy")
    if method == 0x02:
        user = (upstream.username or "").encode()
        password = (upstream.password or "").encode()
        if len(user) > 255 or len(password) > 255:
            raise UpstreamError("SOCKS5 credentials are limited to 255 bytes")
        writer.write(b"\x01" + bytes([len(user)]) + user + bytes([len(password)]) + password)
        await writer.drain()
        _, status = await reader.readexactly(2)
        if status != 0:
            raise UpstreamError("SOCKS5 authentication failed")
    elif method != 0x00:
        raise UpstreamError("SOCKS5 proxy requires an authentication method we do not have")

    try:
        ip = ipaddress.ip_address(host)
        address = (b"\x01" if ip.version == 4 else b"\x04") + ip.packed
    except ValueError:
        name = host.encode("idna")
        address = b"\x03" + bytes([len(name)]) + name
    writer.write(b"\x05\x01\x00" + address + port.to_bytes(2, "big"))
    await writer.drain()
    _, rep, _, atyp = await reader.readexactly(4)
    if atyp == 1:
        await reader.readexactly(4 + 2)
    elif atyp == 4:
        await reader.readexactly(16 + 2)
    elif atyp == 3:
        (length,) = await reader.readexactly(1)
        await reader.readexactly(length + 2)
    if rep != 0:
        raise UpstreamError(
            f"SOCKS5 connect to {host}:{port} failed: {_SOCKS_REPLIES.get(rep, rep)}"
        )


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(_BUFFER):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, OSError, asyncio.IncompleteReadError):
        pass
    finally:
        with contextlib.suppress(Exception):
            if writer.can_write_eof():
                writer.write_eof()


async def _close(writer: asyncio.StreamWriter) -> None:
    writer.close()
    with contextlib.suppress(Exception):
        await writer.wait_closed()


def _rewrite_request(head: bytes, origin_form: bool, auth: str | None) -> bytes:
    """Drop hop-by-hop proxy headers, force Connection: close, optionally add auth."""
    lines = head.decode("latin-1").split("\r\n")
    method, target, version = lines[0].split(" ", 2)
    if origin_form:
        parts = urlsplit(target)
        target = parts.path or "/"
        if parts.query:
            target += "?" + parts.query
    out = [f"{method} {target} {version}"]
    for line in lines[1:]:
        if not line:
            continue
        name = line.split(":", 1)[0].strip().lower()
        if name not in _HOP_HEADERS:
            out.append(line)
    if auth:
        out.append(f"Proxy-Authorization: {auth}")
    out.append("Connection: close")
    return ("\r\n".join(out) + "\r\n\r\n").encode("latin-1")


class ProxyBridge:
    """Loopback HTTP proxy forwarding through an authenticated upstream proxy."""

    def __init__(self, upstream: Upstream, host: str = "127.0.0.1") -> None:
        self.upstream = upstream
        self.host = host
        self.port = 0
        self.connections = 0
        self.errors: deque[str] = deque(maxlen=20)
        self._server: asyncio.base_events.Server | None = None
        self._clients: set[asyncio.Task] = set()

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    async def start(self) -> ProxyBridge:
        self._server = await asyncio.start_server(self._accept, self.host, 0, limit=_HEAD_LIMIT)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            for task in list(self._clients):
                task.cancel()
            await asyncio.gather(*self._clients, return_exceptions=True)
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None

    async def __aenter__(self) -> ProxyBridge:
        return await self.start()

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task:
            self._clients.add(task)
        try:
            await self._handle(reader, writer)
        except asyncio.CancelledError:
            pass
        except Exception as e:  # one bad connection must not stop the bridge
            self.errors.append(f"{type(e).__name__}: {e}")
        finally:
            await _close(writer)
            if task:
                self._clients.discard(task)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await _read_head(reader)
        except (asyncio.IncompleteReadError, ConnectionError):
            return
        request_line = head.split(b"\r\n", 1)[0].decode("latin-1")
        parts = request_line.split(" ")
        if len(parts) != 3:
            writer.write(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
            return
        method, target, _ = parts
        self.connections += 1

        connect = method.upper() == "CONNECT"
        try:
            if connect:
                host, port = _split_host_port(target, 443)
            else:
                url = urlsplit(target)
                if url.scheme != "http" or not url.hostname:
                    raise ValueError("not an absolute http:// URL")
                host, port = url.hostname, url.port or 80
            if not 0 < port < 65536:
                raise ValueError("port out of range")
        except ValueError:
            writer.write(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
            return

        up_writer: asyncio.StreamWriter | None = None
        try:
            try:
                if not connect and self.upstream.scheme in ("http", "https"):
                    # Plain HTTP through an HTTP proxy: forward the absolute-form request.
                    up_reader, up_writer = await self._open_upstream_raw()
                    prefix = _rewrite_request(
                        head, origin_form=False, auth=self.upstream.basic_auth()
                    )
                else:
                    up_reader, up_writer = await open_tunnel(self.upstream, host, port)
                    prefix = b"" if connect else _rewrite_request(head, True, None)
            except (OSError, UpstreamError, asyncio.TimeoutError, asyncio.IncompleteReadError) as e:
                message = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
                self.errors.append(f"{host}:{port}: {message}")
                writer.write(
                    b"HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\n"
                    + message.encode("utf-8", "replace")
                )
                return

            if connect:
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
            else:
                up_writer.write(prefix)
                await up_writer.drain()
            await asyncio.gather(_pipe(reader, up_writer), _pipe(up_reader, writer))
        finally:
            if up_writer is not None:
                await _close(up_writer)

    async def _open_upstream_raw(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        use_tls = ssl.create_default_context() if self.upstream.scheme == "https" else None
        return await asyncio.wait_for(
            asyncio.open_connection(
                self.upstream.host,
                self.upstream.port,
                ssl=use_tls,
                server_hostname=self.upstream.host if use_tls else None,
            ),
            CONNECT_TIMEOUT,
        )
