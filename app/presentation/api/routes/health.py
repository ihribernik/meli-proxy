from collections.abc import Awaitable
from typing import Dict

from fastapi import APIRouter

from app.infrastructure.redis_client import get_redis

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> Dict[str, Dict[str, str] | str]:
    status = "healthy"
    redis_status = "connected"
    try:
        r = await get_redis()
        ping_result: bool | Awaitable[bool] = r.ping()
        pong = (
            await ping_result
            if isinstance(ping_result, Awaitable)
            else bool(ping_result)
        )

        if not pong:
            status = "unhealthy"
            redis_status = "no_pong"
    except Exception as e:
        status = "unhealthy"
        redis_status = str(e)

    return {
        "status": status,
        "redis": {
            "status": "healthy" if status == "healthy" else "unhealthy",
            "details": redis_status,
        },
    }
