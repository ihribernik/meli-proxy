from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import Settings
from app.presentation.api.dependencies import require_admin_token
from app.presentation.api.middlewares.rate_limit import (
    RedisRateLimiter,
    get_rate_limiter,
)
from app.presentation.schemas import (
    RateLimitIPPathRule,
    RateLimitRules,
    RateLimitRulesPatch,
)


router = APIRouter(
    prefix="/admin/rate-limits",
    tags=["Rate Limits"],
    dependencies=[Depends(require_admin_token)],
)


@router.get("", response_model=RateLimitRules)
async def get_rate_limit_rules(
    limiter: RedisRateLimiter = Depends(get_rate_limiter),
) -> RateLimitRules:
    rules = await limiter.get_rules()
    return RateLimitRules.model_validate(rules)


@router.put("", response_model=RateLimitRules, status_code=status.HTTP_200_OK)
async def replace_rate_limit_rules(
    payload: RateLimitRules,
    limiter: RedisRateLimiter = Depends(get_rate_limiter),
) -> RateLimitRules:
    await limiter.set_rules(
        ip_rules=dict(payload.ip),
        path_rules=dict(payload.path),
        ip_path_rules=[rule.model_dump() for rule in payload.ip_path],
    )
    refreshed = await limiter.get_rules()
    return RateLimitRules.model_validate(refreshed)


@router.patch("", response_model=RateLimitRules, status_code=status.HTTP_200_OK)
async def patch_rate_limit_rules(
    payload: RateLimitRulesPatch,
    limiter: RedisRateLimiter = Depends(get_rate_limiter),
) -> RateLimitRules:
    current = await limiter.get_rules()

    if payload.ip is None and payload.path is None and payload.ip_path is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of 'ip', 'path' or 'ip_path' must be provided.",
        )

    next_ip = dict(payload.ip) if payload.ip is not None else dict(current["ip"])
    next_path = (
        dict(payload.path) if payload.path is not None else dict(current["path"])
    )
    next_ip_path = (
        [rule.model_dump() for rule in payload.ip_path]
        if payload.ip_path is not None
        else list(current["ip_path"])
    )

    await limiter.set_rules(
        ip_rules=next_ip,
        path_rules=next_path,
        ip_path_rules=next_ip_path,
    )
    refreshed = await limiter.get_rules()
    return RateLimitRules.model_validate(refreshed)


@router.post(
    "/reset",
    response_model=RateLimitRules,
    status_code=status.HTTP_200_OK,
)
async def reset_rate_limit_rules(
    limiter: RedisRateLimiter = Depends(get_rate_limiter),
) -> RateLimitRules:
    settings = Settings()
    defaults = RateLimitRules(
        ip=settings.RATE_LIMIT_RULES_IP,
        path=settings.RATE_LIMIT_RULES_PATH,
        ip_path=settings.RATE_LIMIT_RULES_IP_PATH,
    )

    await limiter.set_rules(
        ip_rules=dict(defaults.ip),
        path_rules=dict(defaults.path),
        ip_path_rules=[rule.model_dump() for rule in defaults.ip_path],
    )
    refreshed = await limiter.get_rules()
    return RateLimitRules.model_validate(refreshed)
