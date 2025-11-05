import unittest

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.fast_api import app


class DummyRedis:
    async def ping(self) -> bool:
        return True


class DummyLimiter:
    async def check_and_increment(
        self, *args: tuple, **kwargs: dict
    ) -> tuple[bool, None, int, int]:
        # allowed, rule, remaining, reset_in
        return True, None, 0, 0


class HealthTest(unittest.TestCase):

    def setUp(self) -> None:
        self.monkeypatch = MonkeyPatch()
        self.client = TestClient(app)

    def test_health_ok(self) -> None:
        # Monkeypatch Redis client used by health endpoint
        from app.presentation.api.routes import health as health_module

        async def dummy_get_redis() -> DummyRedis:
            return DummyRedis()

        self.monkeypatch.setattr(
            health_module, "get_redis", dummy_get_redis, raising=True
        )

        # Monkeypatch rate limiter to avoid hitting Redis
        from app.presentation.api.middlewares import rate_limit as rl

        self.monkeypatch.setattr(
            rl, "get_rate_limiter", lambda: DummyLimiter(), raising=True
        )

        resp = self.client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["redis"]["status"], "healthy")
        self.assertEqual(data["redis"]["details"], "connected")

    def test_health_ok_exception(self) -> None:
        # Monkeypatch Redis client used by health endpoint
        from app.presentation.api.routes import health as health_module

        async def dummy_get_redis() -> DummyRedis:
            raise Exception("bad")

        self.monkeypatch.setattr(
            health_module, "get_redis", dummy_get_redis, raising=True
        )

        # Monkeypatch rate limiter to avoid hitting Redis
        from app.presentation.api.middlewares import rate_limit as rl

        self.monkeypatch.setattr(
            rl, "get_rate_limiter", lambda: DummyLimiter(), raising=True
        )

        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "unhealthy")
        self.assertEqual(data["redis"]["status"], "unhealthy")
        self.assertEqual(data["redis"]["details"], "bad")

    def test_health_ko(self) -> None:
        # Monkeypatch Redis client used by health endpoint
        from app.presentation.api.routes import health as health_module

        async def dummy_get_redis() -> DummyRedis:
            dummy = DummyRedis()

            async def bad_ping() -> bool:
                return False

            dummy.ping = bad_ping
            return dummy

        self.monkeypatch.setattr(
            health_module, "get_redis", dummy_get_redis, raising=True
        )

        # Monkeypatch rate limiter to avoid hitting Redis
        from app.presentation.api.middlewares import rate_limit as rl

        self.monkeypatch.setattr(
            rl, "get_rate_limiter", lambda: DummyLimiter(), raising=True
        )

        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "unhealthy")
        self.assertEqual(data["redis"]["status"], "unhealthy")
        self.assertEqual(data["redis"]["details"], "no_pong")

    def test_health_ko_exception(self) -> None:
        # Monkeypatch Redis client used by health endpoint
        from app.presentation.api.routes import health as health_module

        async def dummy_get_redis() -> DummyRedis:
            raise Exception("bad")

        self.monkeypatch.setattr(
            health_module, "get_redis", dummy_get_redis, raising=True
        )

        # Monkeypatch rate limiter to avoid hitting Redis
        from app.presentation.api.middlewares import rate_limit as rl

        self.monkeypatch.setattr(
            rl, "get_rate_limiter", lambda: DummyLimiter(), raising=True
        )

        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "unhealthy")
        self.assertEqual(data["redis"]["status"], "unhealthy")
        self.assertEqual(data["redis"]["details"], "bad")
