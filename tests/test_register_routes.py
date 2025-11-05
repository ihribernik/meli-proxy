import types
import unittest
from typing import Any, Iterator, Tuple

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.presentation.api.routes import register_routes


class TestRegisterRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self.monkeypatch = MonkeyPatch()

    def tearDown(self) -> None:
        self.monkeypatch.undo()

    def _fake_iter_modules(self) -> Iterator[Tuple[Any, str, bool]]:
        # (module_finder, module_name, is_pkg)
        yield (None, "a_pkg", True)  # should be skipped by `continue`
        yield (None, "no_router", False)  # module without `router`
        yield (None, "with_router", False)  # module with `router`

    def test_register_routes_includes_router_and_logs(self) -> None:
        # Prepare a dummy module with a router and one endpoint
        mod_with_router = types.SimpleNamespace()
        router = APIRouter()

        @router.get("/ok")
        async def ok() -> dict[str, str]:  # pragma: no cover - trivial
            return {"status": "ok"}

        mod_with_router.router = router

        # Prepare a dummy module without router
        mod_without_router = types.SimpleNamespace()

        # Monkeypatch pkgutil.iter_modules and importlib.import_module
        import importlib
        import pkgutil

        from app.presentation.api import routes as routes_pkg

        self.monkeypatch.setattr(
            pkgutil,
            "iter_modules",
            lambda _path: self._fake_iter_modules(),
            raising=True,
        )

        def fake_import(name: str, package: str | None = None) -> Any:
            if name.endswith(".with_router"):
                return mod_with_router
            if name.endswith(".no_router"):
                return mod_without_router
            # Should not be called for packages as is_pkg True is skipped
            raise ImportError(name)

        self.monkeypatch.setattr(importlib, "import_module", fake_import, raising=True)

        # Spy logger.warning to ensure it's called for the router module
        from fastapi.logger import logger

        calls: list[str] = []

        def fake_warning(msg: str) -> None:
            calls.append(msg)

        self.monkeypatch.setattr(logger, "warning", fake_warning, raising=True)

        # Run register_routes against a fresh FastAPI app
        app = FastAPI()
        register_routes(app, prefix="/api")

        # It should have registered the router route at /api/ok
        client = TestClient(app)
        resp = client.get("/api/ok")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # Logger was called for the module with a router
        assert any("with_router" in m for m in calls)

    def test_register_routes_skips_packages_and_modules_without_router(self) -> None:
        # Only yield a package and a module without router
        def fake_iter_modules_only_skips() -> Iterator[Tuple[Any, str, bool]]:
            yield (None, "a_pkg", True)
            yield (None, "no_router", False)

        import importlib
        import pkgutil

        self.monkeypatch.setattr(
            pkgutil,
            "iter_modules",
            lambda _path: fake_iter_modules_only_skips(),
            raising=True,
        )

        def fake_import(name: str, package: str | None = None) -> Any:
            # Return a module without router
            return types.SimpleNamespace()

        self.monkeypatch.setattr(importlib, "import_module", fake_import, raising=True)

        app = FastAPI()
        register_routes(app, prefix="/api")

        # There should be no route at /api/ok since nothing was included
        client = TestClient(app)
        resp = client.get("/api/ok")
        assert resp.status_code == 404
