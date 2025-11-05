from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import Settings
from app.presentation.api.middlewares.rate_limit import rate_limit_middleware
from app.presentation.api.routes import register_routes
from app.presentation.proxy import router as proxy_router

load_dotenv()


def create_app() -> FastAPI:
    settings = Settings()

    app = FastAPI(
        title=settings.API_TITLE,
        version=settings.API_VERSION,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limit middleware (Redis backed)
    app.middleware("http")(rate_limit_middleware)

    # Health and other small routes
    register_routes(app, prefix="")

    # Prometheus metrics at /metrics (place before proxy)
    Instrumentator().instrument(app).expose(
        app, endpoint="/metrics", include_in_schema=False
    )

    # Proxy all other paths to Mercado Libre
    app.include_router(proxy_router, prefix="")

    return app


app = create_app()
