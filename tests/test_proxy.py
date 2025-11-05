import unittest

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

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
        self.monkeypatch.setattr(proxy_module, "_client", dummy_client, raising=True)

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
        proxy._client = None

    def tearDown(self) -> None:
        # deshacer parches
        self.monkeypatch.undo()

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
