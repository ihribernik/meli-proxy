from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.fast_api as fast_api


class FastAPICreationTest(unittest.TestCase):
    def test_create_app_uses_settings_and_registers_routes(self) -> None:
        instrumentator = MagicMock()
        instrumentator.instrument.return_value = instrumentator

        with patch.object(fast_api, "Instrumentator", return_value=instrumentator), patch.object(
            fast_api, "Settings"
        ) as settings_cls:
            settings_cls.return_value = SimpleNamespace(
                API_TITLE="Test API",
                API_VERSION="0.0.1",
                CORS_ORIGINS=["http://example.com"],
            )
            app = fast_api.create_app()

        self.assertEqual(app.title, "Test API")
        self.assertEqual(app.version, "0.0.1")

        cors_origins = None
        for middleware in app.user_middleware:
            if getattr(middleware.cls, "__name__", "") == "CORSMiddleware":
                cors_origins = middleware.kwargs.get("allow_origins")
                break

        self.assertEqual(cors_origins, ["http://example.com"])
        self.assertTrue(any(route.path == "/health" for route in app.routes))
        instrumentator.instrument.assert_called_once_with(app)
        instrumentator.expose.assert_called_once()
        _, kwargs = instrumentator.expose.call_args
        self.assertEqual(kwargs.get("endpoint"), "/metrics")
        self.assertFalse(kwargs.get("include_in_schema", True))
