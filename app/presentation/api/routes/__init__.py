from __future__ import annotations

import importlib
import pkgutil

from fastapi import FastAPI
from fastapi.logger import logger


def register_routes(app: FastAPI, prefix: str = "/api") -> None:
    package = __name__
    for _, module_name, is_pkg in pkgutil.iter_modules(__path__):
        if is_pkg:
            continue

        module = importlib.import_module(f"{package}.{module_name}")
        if hasattr(module, "router"):
            logger.warning(f"Registering {module_name} router")
            app.include_router(module.router, prefix=prefix)
