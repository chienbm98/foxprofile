import asyncio
import json
from collections import deque

import pytest

from chrome_engine.proxy_bridge import ProxyBridge, Upstream, open_tunnel

from .servers import HttpProxy, Origin, Socks5Proxy, http_get_via_connect, http_get_via_proxy


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, 30))


# --- parsing ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("http://u:p@1.2.3.4:8080", Upstream("http", "1.2.3.4", 8080, "u", "p")),
        ("1.2.3.4:8080", Upstream("http", "1.2.3.4", 8080)),
        ("1.2.3.4:8080:user:pass", Upstream("http", "1.2.3.4", 8080, "user", "pass")),
        ("socks5://u:p@h.example:1080", Upstream("socks5", "h.example", 1080, "u", "p")),
        ("socks5h://h.example:1080", Upstream("socks5", "h.example", 1080)),
        ("https://proxy.example:443", Upstream("https", "proxy.example", 443)),
        ("http://us%40er:p%3Aw%2Fd@h:1", Upstream("http", "h", 1, "us@er", "p:w/d")),
    ],
)
def test_parse(text, expected):
    assert Upstream.parse(text) == expected


@pytest.mark.parametrize(
    "text", ["socks4://h:1", "ftp://h:1", "http://h", "http://:80", "h:notaport"]
)
def test_parse_rejects(text):
    with pytest.raises(ValueError):
        Upstream.parse(text)


def test_basic_auth_header():
    assert Upstream("http", "h", 1, "user", "pass").basic_auth() == "Basic dXNlcjpwYXNz"
    assert Upstream("http", "h", 1).basic_auth() is None


# --- forwarding --------------------------------------------------------------


async def _with_servers(test, proxy_cls):
    origin = await Origin().start()
    upstream = await proxy_cls().start()
    bridge = await ProxyBridge(Upstream.parse(upstream.url)).start()
    try:
        await test(origin, upstream, bridge)
    finally:
        await bridge.stop()
        await upstream.stop()
        await origin.stop()


@pytest.mark.parametrize("proxy_cls", [HttpProxy, Socks5Proxy])
def test_connect_tunnel_through_authenticated_upstream(proxy_cls):
    async def test(origin, upstream, bridge):
        status, body = await http_get_via_connect(bridge.port, "127.0.0.1", origin.port)
        assert status == 200
        assert b"origin-ok" in body
        assert origin.hits == ["/"]

    run(_with_servers(test, proxy_cls))


@pytest.mark.parametrize("proxy_cls", [HttpProxy, Socks5Proxy])
def test_plain_http_through_authenticated_upstream(proxy_cls):
    async def test(origin, upstream, bridge):
        status, body = await http_get_via_proxy(bridge.port, f"{origin.url}/echo?x=1")
        assert status == 200
        echoed = json.loads(body)
        assert echoed["path"] == "/echo?x=1"
        # Proxy credentials and hop-by-hop proxy headers never reach the origin.
        assert not any(h.lower().startswith("proxy-") for h in echoed["headers"])

    run(_with_servers(test, proxy_cls))


def test_http_upstream_receives_credentials_and_target():
    async def test(origin, upstream, bridge):
        await http_get_via_connect(bridge.port, "localhost", origin.port)
        assert upstream.requests == [("CONNECT", f"localhost:{origin.port}")]
        assert upstream.rejected == 0

    run(_with_servers(test, HttpProxy))


def test_socks_upstream_resolves_names_remotely():
    async def test(origin, upstream, bridge):
        await http_get_via_connect(bridge.port, "localhost", origin.port)
        # The hostname went to the proxy as a name: no local DNS lookup.
        assert upstream.targets == [("domain", "localhost", origin.port)]

    run(_with_servers(test, Socks5Proxy))


def test_socks_upstream_ip_targets_use_ip_addressing():
    async def test(origin, upstream, bridge):
        await http_get_via_connect(bridge.port, "127.0.0.1", origin.port)
        assert upstream.targets == [("ipv4", "127.0.0.1", origin.port)]

    run(_with_servers(test, Socks5Proxy))


@pytest.mark.parametrize("proxy_cls", [HttpProxy, Socks5Proxy])
def test_wrong_credentials_give_502(proxy_cls):
    async def test():
        origin = await Origin().start()
        upstream = await proxy_cls().start()
        good = Upstream.parse(upstream.url)
        bad = Upstream(good.scheme, good.host, good.port, good.username, "wrong")
        bridge = await ProxyBridge(bad).start()
        try:
            status, _ = await http_get_via_connect(bridge.port, "127.0.0.1", origin.port)
            assert status == 502
            assert origin.hits == []
            assert bridge.errors
        finally:
            await bridge.stop()
            await upstream.stop()
            await origin.stop()

    run(test())


def test_upstream_down_gives_502():
    async def test():
        dead = await HttpProxy().start()
        port = dead.port
        await dead.stop()
        bridge = await ProxyBridge(Upstream("http", "127.0.0.1", port, "u", "p")).start()
        try:
            status, _ = await http_get_via_connect(bridge.port, "example.com", 443)
            assert status == 502
        finally:
            await bridge.stop()

    run(test())


def test_target_unreachable_via_socks_gives_502():
    async def test():
        upstream = await Socks5Proxy().start()
        closed = await Origin().start()
        port = closed.port
        await closed.stop()
        bridge = await ProxyBridge(Upstream.parse(upstream.url)).start()
        try:
            status, _ = await http_get_via_connect(bridge.port, "127.0.0.1", port)
            assert status == 502
            assert "connection refused" in bridge.errors[-1]
        finally:
            await bridge.stop()
            await upstream.stop()

    run(test())


def test_malformed_request_gives_400():
    async def test():
        bridge = await ProxyBridge(Upstream("http", "127.0.0.1", 9)).start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", bridge.port)
            writer.write(b"NONSENSE\r\n\r\n")
            await writer.drain()
            assert (await reader.read()).startswith(b"HTTP/1.1 400")
            writer.close()
        finally:
            await bridge.stop()

    run(test())


def test_many_concurrent_tunnels():
    async def test(origin, upstream, bridge):
        results = await asyncio.gather(
            *(http_get_via_connect(bridge.port, "127.0.0.1", origin.port) for _ in range(25))
        )
        assert all(status == 200 for status, _ in results)
        assert bridge.connections == 25

    run(_with_servers(test, Socks5Proxy))


def test_large_body_is_streamed_intact():
    async def test(origin, upstream, bridge):
        reader, writer = await asyncio.open_connection("127.0.0.1", bridge.port)
        writer.write(f"CONNECT 127.0.0.1:{origin.port} HTTP/1.1\r\n\r\n".encode())
        await writer.drain()
        assert (await reader.readuntil(b"\r\n\r\n")).startswith(b"HTTP/1.1 200")
        payload = b"x" * (3 * 1024 * 1024)
        writer.write(
            f"POST /echo HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: {len(payload)}\r\n"
            "Content-Type: text/plain\r\nConnection: close\r\n\r\n".encode()
            + payload
        )
        await writer.drain()
        data = await reader.read()
        writer.close()
        body = json.loads(data.split(b"\r\n\r\n", 1)[1])
        assert body["body"] == payload.decode()

    run(_with_servers(test, Socks5Proxy))


def test_stop_closes_open_tunnels():
    async def test(origin, upstream, bridge):
        reader, writer = await asyncio.open_connection("127.0.0.1", bridge.port)
        writer.write(f"CONNECT 127.0.0.1:{origin.port} HTTP/1.1\r\n\r\n".encode())
        await writer.drain()
        await reader.readuntil(b"\r\n\r\n")
        await bridge.stop()
        assert await asyncio.wait_for(reader.read(), 5) == b""

    run(_with_servers(test, HttpProxy))


def test_open_tunnel_directly():
    async def test(origin, upstream, bridge):
        reader, writer = await open_tunnel(Upstream.parse(upstream.url), "127.0.0.1", origin.port)
        writer.write(b"GET / HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
        await writer.drain()
        assert b"origin-ok" in await reader.read()
        writer.close()

    run(_with_servers(test, HttpProxy))


@pytest.mark.parametrize("target", ["example.com:abc", "example.com:0", "example.com:70000"])
def test_bad_connect_port_gives_400(target):
    async def test():
        bridge = await ProxyBridge(Upstream("http", "127.0.0.1", 9)).start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", bridge.port)
            writer.write(f"CONNECT {target} HTTP/1.1\r\n\r\n".encode())
            await writer.drain()
            assert (await reader.read()).startswith(b"HTTP/1.1 400")
            writer.close()
            assert bridge.errors == deque()
        finally:
            await bridge.stop()

    run(test())


@pytest.mark.parametrize(
    ("authority", "expected"),
    [
        ("example.com:8443", ("example.com", 8443)),
        ("example.com", ("example.com", 443)),
        ("[::1]:8080", ("::1", 8080)),
        ("[2001:db8::1]", ("2001:db8::1", 443)),
    ],
)
def test_split_host_port(authority, expected):
    from chrome_engine.proxy_bridge import _split_host_port

    assert _split_host_port(authority, 443) == expected


def test_non_http_absolute_target_gives_400():
    async def test():
        bridge = await ProxyBridge(Upstream("http", "127.0.0.1", 9)).start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", bridge.port)
            writer.write(b"GET ftp://example.com/ HTTP/1.1\r\n\r\n")
            await writer.drain()
            assert (await reader.read()).startswith(b"HTTP/1.1 400")
            writer.close()
        finally:
            await bridge.stop()

    run(test())
