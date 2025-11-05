from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from app.core.config import Settings

_api_key_header = APIKeyHeader(name="X-Admin-Token", auto_error=False)


async def require_admin_token(api_key: str | None = Depends(_api_key_header)) -> str:
    settings = Settings()
    allowed = settings.ADMIN_API_KEYS

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin API disabled.",
        )

    if api_key is None or api_key not in allowed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token.",
        )

    return api_key
