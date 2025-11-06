import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from starlette.requests import Request

import app.fast_api as fast_api


class DummyUpstreamResp:
    def __init__(self, content: bytes, status_code: int, headers: dict[str, str]):
        self.content = content
        self.status_code = status_code
        self.headers = headers


class DummyClient:
    def __init__(self, response: DummyUpstreamResp):
        self._resp = response
        self.captured_request: dict[str, object] = {}

    async def request(self, *args: tuple, **kwargs: dict) -> DummyUpstreamResp:
        if args:
            self.captured_request["args"] = args
        if kwargs:
            self.captured_request["kwargs"] = kwargs
        return self._resp


class DummyLimiter:
    async def check_and_increment(
        self, client_ip: str, path: str
    ) -> tuple[bool, None, int, int]:
        return True, None, 0, 0


created = {"count": 0}


class ProxyTest(unittest.TestCase):

    def setUp(self) -> None:
        self.monkeypatch = MonkeyPatch()

    def test_proxy_forwards_response(
        self,
    ) -> None:
        # Stub upstream httpx client
        from app.presentation import proxy as proxy_module

        dummy_resp = DummyUpstreamResp(
            b'{"ok":true}', 200, {"content-type": "application/json"}
        )
        dummy_client = DummyClient(dummy_resp)
        proxy_module._ProxyAsyncClientSingleton.set_client(dummy_client)
        self.addCleanup(proxy_module._ProxyAsyncClientSingleton.set_client, None)

        # Stub rate limiter to avoid Redis
        from app.presentation.api.middlewares import rate_limit as rl

        self.monkeypatch.setattr(
            rl, "get_rate_limiter", lambda: DummyLimiter(), raising=True
        )

        client = TestClient(fast_api.app)
        r = client.get("/categories/MLA97994?foo=bar")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "application/json")
        self.assertEqual(r.text, '{"ok":true}')
        captured_headers = dummy_client.captured_request["kwargs"]["headers"]
        self.assertIn("X-Forwarded-For", captured_headers)
        self.assertIn("X-Forwarded-Host", captured_headers)
        self.assertIn("X-Forwarded-Proto", captured_headers)


class TestProxyLazyClient(unittest.TestCase):
    def setUp(self) -> None:
        # Resetear el singleton antes de cada test
        import app.presentation.proxy as proxy

        self.monkeypatch = MonkeyPatch()
        proxy._ProxyAsyncClientSingleton.set_client(None)

    def tearDown(self) -> None:
        # deshacer parches
        self.monkeypatch.undo()
        import app.presentation.proxy as proxy

        proxy._ProxyAsyncClientSingleton.set_client(None)

    def test_lazy_client_initialized_once(self) -> None:
        import app.presentation.proxy as proxy

        created: dict = {"count": 0}

        class DummyAsyncClient:
            def __init__(self, *args: tuple, **kwargs: dict) -> None:
                created["count"] += 1

        # parchear el constructor de httpx.AsyncClient
        self.monkeypatch.setattr(
            "app.presentation.proxy.httpx.AsyncClient", DummyAsyncClient, raising=True
        )

        c1 = proxy._get_client()
        c2 = proxy._get_client()

        self.assertIs(c1, c2)
        self.assertEqual(created["count"], 1)

    def test_client_constructor_kwargs_shape(self) -> None:
        import app.presentation.proxy as proxy

        captured: dict = {"kwargs": None}

        class DummyAsyncClient:
            def __init__(self, *args: tuple, **kwargs: dict) -> None:
                captured["kwargs"] = kwargs

        self.monkeypatch.setattr(
            "app.presentation.proxy.httpx.AsyncClient", DummyAsyncClient, raising=True
        )

        _ = proxy._get_client()

        self.assertIsNotNone(captured["kwargs"])
        kwargs = captured["kwargs"]
        self.assertIn("follow_redirects", kwargs)
        self.assertFalse(kwargs["follow_redirects"])
        self.assertIn("timeout", kwargs)
        self.assertIn("limits", kwargs)


def _make_request(
    headers: list[tuple[bytes, bytes]],
    client: tuple[str, int] | None = ("127.0.0.1", 12345),
    scheme: str = "http",
) -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "path": "/proxy/test",
        "raw_path": b"/proxy/test",
        "headers": headers,
        "query_string": b"",
        "client": client,
        "scheme": scheme,
        "server": ("testserver", 80),
        "root_path": "",
    }
    body_sent = {"value": False}

    async def receive() -> dict:
        if body_sent["value"]:
            return {"type": "http.disconnect"}
        body_sent["value"] = True
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


class TestProxyHeaderEdgeCases(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.monkeypatch = MonkeyPatch()
        from app.presentation import proxy as proxy_module

        self.proxy_module = proxy_module
        self.proxy_module._ProxyAsyncClientSingleton.set_client(None)

    async def asyncTearDown(self) -> None:
        self.proxy_module._ProxyAsyncClientSingleton.set_client(None)
        self.monkeypatch.undo()

    async def test_skips_forwarded_for_when_no_client_ip(self) -> None:
        dummy_resp = DummyUpstreamResp(b"{}", 200, {"content-type": "application/json"})
        dummy_client = DummyClient(dummy_resp)
        self.proxy_module._ProxyAsyncClientSingleton.set_client(dummy_client)
        self.monkeypatch.setattr(
            self.proxy_module,
            "Settings",
            lambda: SimpleNamespace(PROXY_UPSTREAM_BASE="https://upstream.test"),
            raising=True,
        )
        request = _make_request(
            headers=[(b"x-forwarded-for", b"   ")],
            client=None,
            scheme="https",
        )

        response = await self.proxy_module.proxy_all("proxy/test", request)

        self.assertEqual(response.status_code, 200)
        sent_headers = dummy_client.captured_request["kwargs"]["headers"]
        self.assertNotIn("X-Forwarded-For", sent_headers)

    async def test_sets_forwarded_for_from_client_host(self) -> None:
        dummy_resp = DummyUpstreamResp(b"{}", 200, {"content-type": "application/json"})
        dummy_client = DummyClient(dummy_resp)
        self.proxy_module._ProxyAsyncClientSingleton.set_client(dummy_client)
        self.monkeypatch.setattr(
            self.proxy_module,
            "Settings",
            lambda: SimpleNamespace(PROXY_UPSTREAM_BASE="https://upstream.test"),
            raising=True,
        )
        request = _make_request(
            headers=[],
            client=("203.0.113.1", 4242),
        )

        response = await self.proxy_module.proxy_all("proxy/test", request)

        self.assertEqual(response.status_code, 200)
        sent_headers = dummy_client.captured_request["kwargs"]["headers"]
        self.assertEqual(sent_headers["X-Forwarded-For"], "203.0.113.1")

    async def test_does_not_duplicate_forward_chain(self) -> None:
        dummy_resp = DummyUpstreamResp(b"{}", 200, {"content-type": "application/json"})
        dummy_client = DummyClient(dummy_resp)
        self.proxy_module._ProxyAsyncClientSingleton.set_client(dummy_client)
        self.monkeypatch.setattr(
            self.proxy_module,
            "Settings",
            lambda: SimpleNamespace(PROXY_UPSTREAM_BASE="https://upstream.test"),
            raising=True,
        )
        request = _make_request(
            headers=[(b"x-forwarded-for", b"1.1.1.1")],
            client=("10.0.0.2", 5000),
        )

        response = await self.proxy_module.proxy_all("proxy/test", request)

        self.assertEqual(response.status_code, 200)
        sent_headers = dummy_client.captured_request["kwargs"]["headers"]
        self.assertEqual(sent_headers["X-Forwarded-For"], "1.1.1.1")
        self.assertTrue(
            all(
                key.lower() != "x-forwarded-for" or key == "X-Forwarded-For"
                for key in sent_headers
            )
        )

    async def test_respects_existing_forwarded_host_and_proto(self) -> None:
        dummy_resp = DummyUpstreamResp(b"{}", 200, {"content-type": "application/json"})
        dummy_client = DummyClient(dummy_resp)
        self.proxy_module._ProxyAsyncClientSingleton.set_client(dummy_client)
        self.monkeypatch.setattr(
            self.proxy_module,
            "Settings",
            lambda: SimpleNamespace(PROXY_UPSTREAM_BASE="https://upstream.test"),
            raising=True,
        )
        request = _make_request(
            headers=[
                (b"host", b"incoming.example"),
                (b"x-forwarded-for", b"9.9.9.9"),
                (b"x-forwarded-host", b"already-set"),
                (b"x-forwarded-proto", b"https"),
            ],
            client=("10.0.0.3", 443),
            scheme="https",
        )

        response = await self.proxy_module.proxy_all("proxy/test", request)

        self.assertEqual(response.status_code, 200)
        sent_headers = dummy_client.captured_request["kwargs"]["headers"]
        self.assertNotIn("X-Forwarded-Host", sent_headers)
        self.assertNotIn("X-Forwarded-Proto", sent_headers)
        self.assertEqual(sent_headers["x-forwarded-host"], "already-set")
        self.assertEqual(sent_headers["x-forwarded-proto"], "https")


class TestComposeForwardedFor(unittest.TestCase):
    def test_returns_none_when_client_ip_missing(self) -> None:
        from app.presentation.proxy import _compose_forwarded_for

        result = _compose_forwarded_for("1.1.1.1", "")
        self.assertIsNone(result)

    def test_preserves_existing_chain_without_duplication(self) -> None:
        from app.presentation.proxy import _compose_forwarded_for

        result = _compose_forwarded_for("1.1.1.1", "1.1.1.1")
        self.assertEqual(result, "1.1.1.1")

    def test_appends_new_ip_to_chain(self) -> None:
        from app.presentation.proxy import _compose_forwarded_for

        result = _compose_forwarded_for("1.1.1.1, 2.2.2.2", "3.3.3.3")
        self.assertEqual(result, "1.1.1.1, 2.2.2.2, 3.3.3.3")
