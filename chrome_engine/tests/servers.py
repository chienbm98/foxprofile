"""Small local servers for the tests: an origin, an HTTP proxy and a SOCKS5 proxy.

Both proxies require credentials and record what they were asked for, so tests
can prove that traffic really went through them and with which target names.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json

from aiohttp import web


class Origin:
    """HTTP server: / returns a page, /echo returns the request as JSON."""

    def __init__(self, host: str = "127.0.0.1") -> None:
        self.host = host
        self.port = 0
        self.hits: list[str] = []
        self._runner: web.AppRunner | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    async def start(self) -> Origin:
        async def page(request: web.Request) -> web.Response:
            self.hits.append(request.path)
            return web.Response(
                text="<html><body>origin-ok</body></html>", content_type="text/html"
            )

        async def echo(request: web.Request) -> web.Response:
            self.hits.append(request.path)
            return web.json_response(
                {
                    "path": request.path_qs,
                    "headers": dict(request.headers),
                    "body": await request.text(),
                }
            )

        app = web.Application(client_max_size=16 * 1024 * 1024)
        app.router.add_get("/", page)
        app.router.add_route("*", "/echo", echo)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, 0)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]
        return self

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, OSError):
        pass
    finally:
        with contextlib.suppress(Exception):
            if writer.can_write_eof():
                writer.write_eof()


async def _splice(a: tuple, b: tuple) -> None:
    await asyncio.gather(_pipe(a[0], b[1]), _pipe(b[0], a[1]))
    for w in (a[1], b[1]):
        w.close()


class _Server:
    def __init__(self) -> None:
        self.port = 0
        self._server: asyncio.base_events.Server | None = None
        self._tasks: set[asyncio.Task] = set()

    async def start(self):
        self._server = await asyncio.start_server(self._accept, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            for t in list(self._tasks):
                t.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _accept(self, reader, writer) -> None:
        task = asyncio.current_task()
        self._tasks.add(task)
        try:
            await self.handle(reader, writer)
        except (asyncio.CancelledError, ConnectionError, asyncio.IncompleteReadError, OSError):
            pass
        finally:
            writer.close()
            self._tasks.discard(task)

    async def handle(self, reader, writer) -> None:
        raise NotImplementedError


class HttpProxy(_Server):
    """HTTP proxy (CONNECT and absolute-form) requiring Basic credentials."""

    def __init__(self, username: str = "user", password: str = "p@ss:w/rd") -> None:
        super().__init__()
        self.username = username
        self.password = password
        self.requests: list[tuple[str, str]] = []
        self.rejected = 0

    @property
    def url(self) -> str:
        from urllib.parse import quote

        return f"http://{quote(self.username, safe='')}:{quote(self.password, safe='')}@127.0.0.1:{self.port}"

    def _authorized(self, head: str) -> bool:
        expected = "Basic " + base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        for line in head.split("\r\n")[1:]:
            name, _, value = line.partition(":")
            if name.strip().lower() == "proxy-authorization" and value.strip() == expected:
                return True
        return False

    async def handle(self, reader, writer) -> None:
        head = (await reader.readuntil(b"\r\n\r\n")).decode("latin-1")
        method, target, _ = head.split("\r\n", 1)[0].split(" ", 2)
        if not self._authorized(head):
            self.rejected += 1
            writer.write(b"HTTP/1.1 407 Proxy Authentication Required\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            return
        self.requests.append((method, target))
        if method == "CONNECT":
            host, _, port = target.rpartition(":")
            upstream = await asyncio.open_connection(host.strip("[]"), int(port))
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            await _splice((reader, writer), upstream)
            return
        from urllib.parse import urlsplit

        url = urlsplit(target)
        upstream = await asyncio.open_connection(url.hostname, url.port or 80)
        lines = head.split("\r\n")
        path = url.path + (("?" + url.query) if url.query else "")
        out = [f"{method} {path} {lines[0].rsplit(' ', 1)[1]}"]
        out += [ln for ln in lines[1:] if ln and not ln.lower().startswith("proxy-")]
        upstream[1].write(("\r\n".join(out) + "\r\n\r\n").encode("latin-1"))
        await upstream[1].drain()
        await _splice((reader, writer), upstream)


class Socks5Proxy(_Server):
    """SOCKS5 proxy requiring username/password; records requested targets."""

    def __init__(self, username: str = "sockuser", password: str = "s3cr#t") -> None:
        super().__init__()
        self.username = username
        self.password = password
        self.targets: list[tuple[str, str, int]] = []  # (address type, host, port)
        self.auth_failures = 0

    @property
    def url(self) -> str:
        from urllib.parse import quote

        return f"socks5://{quote(self.username, safe='')}:{quote(self.password, safe='')}@127.0.0.1:{self.port}"

    async def handle(self, reader, writer) -> None:
        ver, n = await reader.readexactly(2)
        methods = await reader.readexactly(n)
        if 2 not in methods:
            writer.write(b"\x05\xff")
            return
        writer.write(b"\x05\x02")
        await writer.drain()
        _, ulen = await reader.readexactly(2)
        user = (await reader.readexactly(ulen)).decode()
        (plen,) = await reader.readexactly(1)
        password = (await reader.readexactly(plen)).decode()
        if (user, password) != (self.username, self.password):
            self.auth_failures += 1
            writer.write(b"\x01\x01")
            await writer.drain()
            return
        writer.write(b"\x01\x00")
        await writer.drain()
        _, cmd, _, atyp = await reader.readexactly(4)
        if atyp == 3:
            (length,) = await reader.readexactly(1)
            host = (await reader.readexactly(length)).decode()
            kind = "domain"
        elif atyp == 1:
            host = ".".join(str(b) for b in await reader.readexactly(4))
            kind = "ipv4"
        else:
            import ipaddress

            host = str(ipaddress.IPv6Address(await reader.readexactly(16)))
            kind = "ipv6"
        port = int.from_bytes(await reader.readexactly(2), "big")
        self.targets.append((kind, host, port))
        try:
            upstream = await asyncio.open_connection(host, port)
        except OSError:
            writer.write(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")
            await writer.drain()
            return
        writer.write(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00")
        await writer.drain()
        await _splice((reader, writer), upstream)


async def http_get_via_proxy(proxy_port: int, url: str) -> tuple[int, bytes]:
    """GET `url` through an HTTP proxy at 127.0.0.1:proxy_port (absolute-form)."""
    reader, writer = await asyncio.open_connection("127.0.0.1", proxy_port)
    from urllib.parse import urlsplit

    host = urlsplit(url).netloc
    writer.write(f"GET {url} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())
    await writer.drain()
    data = await reader.read()
    writer.close()
    status = int(data.split(b" ", 2)[1])
    return status, data.split(b"\r\n\r\n", 1)[1] if b"\r\n\r\n" in data else b""


async def http_get_via_connect(
    proxy_port: int, host: str, port: int, path: str = "/"
) -> tuple[int, bytes]:
    """GET through a CONNECT tunnel opened on an HTTP proxy at 127.0.0.1:proxy_port."""
    reader, writer = await asyncio.open_connection("127.0.0.1", proxy_port)
    writer.write(f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode())
    await writer.drain()
    head = await reader.readuntil(b"\r\n\r\n")
    status = int(head.split(b" ", 2)[1])
    if status != 200:
        writer.close()
        return status, head
    writer.write(
        f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n\r\n".encode()
    )
    await writer.drain()
    data = await reader.read()
    writer.close()
    return int(data.split(b" ", 2)[1]), data.split(b"\r\n\r\n", 1)[1]


def parse_json_body(body: bytes) -> dict:
    return json.loads(body.decode())
