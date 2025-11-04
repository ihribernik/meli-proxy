from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings
from app.presentation.api.middlewares.rate_limit import rate_limit_middleware
from app.presentation.proxy import router as proxy_router
from app.presentation.api.routes import register_routes
from prometheus_fastapi_instrumentator import Instrumentator

load_dotenv()
def create_app() -> FastAPI:
    settings = Settings()

    fastapi_app = FastAPI(
        title=settings.API_TITLE,
        version=settings.API_VERSION,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limit middleware (Redis backed)
    fastapi_app.middleware("http")(rate_limit_middleware)

    # Health and other small routes
    register_routes(fastapi_app, prefix="")

    # Proxy all other paths to Mercado Libre
    fastapi_app.include_router(proxy_router, prefix="")

        # Prometheus metrics at /metrics\n    Instrumentator().instrument(fastapi_app).expose(fastapi_app, endpoint="/metrics", include_in_schema=False)\n\n    return fastapi_app


app = create_app()

