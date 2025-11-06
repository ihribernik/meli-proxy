import unittest

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

import app.fast_api as fast_api
from app.presentation.api.middlewares import rate_limit as rl


class DummyPipeline:
    def __init__(self, store: dict[str, bytes]):
        self.store = store
        self.operations: list[tuple] = []

    def get(self, key: str) -> "DummyPipeline":
        self.operations.append(("get", key))
        return self

    def set(self, key: str, value: str) -> "DummyPipeline":
        self.operations.append(("set", key, value))
        return self

    def incr(self, key: str) -> "DummyPipeline":
        self.operations.append(("incr", key))
        return self

    def expire(self, key: str, ttl: int) -> "DummyPipeline":
        self.operations.append(("expire", key, ttl))
        return self

    async def execute(self) -> list:
        results = []
        for op in self.operations:
            kind = op[0]
            if kind == "get":
                key = op[1]
                results.append(self.store.get(key))
            elif kind == "set":
                key, value = op[1], op[2]
                payload = value.encode() if isinstance(value, str) else value
                self.store[key] = payload
                results.append(True)
            elif kind == "incr":
                key = op[1]
                current = int(self.store.get(key, b"0").decode())
                current += 1
                self.store[key] = str(current).encode()
                results.append(current)
            elif kind == "expire":
                # TTL handling is not needed for the tests; emulate success.
                results.append(True)
        self.operations.clear()
        return results


class DummyRedis:
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self.published: list[tuple[str, str]] = []

    def pipeline(self) -> DummyPipeline:
        return DummyPipeline(self.store)

    async def ping(self) -> bool:
        return True

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1


class RateLimitAdminRoutesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.monkeypatch = MonkeyPatch()
        self.redis = DummyRedis()
        self.monkeypatch.setenv("ADMIN_API_TOKENS", "secret-token")

        async def fake_get_redis() -> DummyRedis:
            return self.redis

        # Ensure the limiter uses our fake Redis and does not retain previous state.
        rl._set_rate_limiter(None)
        self.monkeypatch.setattr(rl, "get_redis", fake_get_redis, raising=True)

        limiter = rl.RedisRateLimiter(rl.Settings())  # type: ignore[attr-defined]
        self.monkeypatch.setattr(rl, "get_rate_limiter", lambda: limiter, raising=True)

        self.client = TestClient(fast_api.app)
        self.headers = {"X-Admin-Token": "secret-token"}

    def tearDown(self) -> None:
        self.client.close()
        rl._set_rate_limiter(None)
        self.monkeypatch.undo()

    def test_get_returns_defaults(self) -> None:
        resp = self.client.get("/admin/rate-limits", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "ip" in data and "path" in data and "ip_path" in data
        assert data["ip"]["152.152.152.152"] == 1000
        assert data["path"]["/categories/"] == 10000
        assert data["ip_path"][0]["ip"] == "152.152.152.152"
        assert data["updated_at"] is None

    def test_put_replaces_rules(self) -> None:
        payload = {
            "ip": {"10.0.0.1": 50},
            "path": {"/items/": 500},
            "ip_path": [{"ip": "10.0.0.1", "path_prefix": "/items/", "limit": 5}],
        }
        resp = self.client.put("/admin/rate-limits", json=payload, headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ip"] == {"10.0.0.1": 50}
        assert data["path"] == {"/items/": 500}
        assert data["ip_path"] == [
            {"ip": "10.0.0.1", "path_prefix": "/items/", "limit": 5}
        ]
        assert data["updated_at"] is not None

        # Subsequent GET should reflect persisted changes.
        resp_get = self.client.get("/admin/rate-limits", headers=self.headers)
        assert resp_get.status_code == 200
        assert resp_get.json() == data
        assert self.redis.published, "Expected publish on rate-limit update"
        channel, message = self.redis.published[-1]
        assert channel == "rl:config:events"
        assert '"10.0.0.1"' in message

    def test_patch_updates_subset(self) -> None:
        # Seed with defaults
        resp = self.client.get("/admin/rate-limits", headers=self.headers)
        assert resp.status_code == 200

        patch_payload = {
            "ip": {"1.1.1.1": 10},
        }
        resp_patch = self.client.patch(
            "/admin/rate-limits", json=patch_payload, headers=self.headers
        )
        assert resp_patch.status_code == 200
        data = resp_patch.json()
        assert data["ip"] == {"1.1.1.1": 10}
        # Defaults should remain for untouched sections.
        assert data["path"]["/categories/"] == 10000

    def test_patch_requires_at_least_one_section(self) -> None:
        resp = self.client.patch(
            "/admin/rate-limits", json={}, headers=self.headers
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == (
            "At least one of 'ip', 'path' or 'ip_path' must be provided."
        )

    def test_reset_restores_defaults(self) -> None:
        self.client.put(
            "/admin/rate-limits",
            json={
                "ip": {"2.2.2.2": 1},
                "path": {},
                "ip_path": [],
            },
            headers=self.headers,
        )
        resp_reset = self.client.post(
            "/admin/rate-limits/reset", headers=self.headers
        )
        assert resp_reset.status_code == 200
        defaults = resp_reset.json()
        assert defaults["ip"]["152.152.152.152"] == 1000
        assert defaults["path"]["/categories/"] == 10000
        assert defaults["ip_path"][0]["path_prefix"] == "/items/"
        assert defaults["updated_at"] is not None

    def test_missing_token_rejected(self) -> None:
        resp = self.client.get("/admin/rate-limits")
        assert resp.status_code == 401

    def test_invalid_token_rejected(self) -> None:
        resp = self.client.get(
            "/admin/rate-limits", headers={"X-Admin-Token": "invalid"}
        )
        assert resp.status_code == 401


class RateLimitAdminAuthDisabledTest(unittest.TestCase):
    def setUp(self) -> None:
        self.monkeypatch = MonkeyPatch()
        self.monkeypatch.delenv("ADMIN_API_TOKENS", raising=False)
        from app.presentation.api.middlewares import rate_limit as rl

        rl._set_rate_limiter(None)
        self.client = TestClient(fast_api.app)

    def tearDown(self) -> None:
        self.client.close()
        from app.presentation.api.middlewares import rate_limit as rl

        rl._set_rate_limiter(None)
        self.monkeypatch.undo()

    def test_admin_routes_disabled_without_tokens(self) -> None:
        resp = self.client.get("/admin/rate-limits")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Admin API disabled."
