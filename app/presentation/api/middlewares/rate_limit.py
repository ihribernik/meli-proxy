from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional, Tuple

from fastapi import Request, Response
from prometheus_client import Counter
from starlette.responses import JSONResponse

from app.core.config import Settings
from app.infrastructure.redis_client import get_redis

RATE_LIMIT_ALLOWED = Counter(
    "meli_proxy_rate_limit_allowed_total",
    "Allowed requests after rate limiting",
    labelnames=["scope"],
)
RATE_LIMIT_BLOCKED = Counter(
    "meli_proxy_rate_limit_blocked_total",
    "Blocked requests by rate limiting",
    labelnames=["scope"],
)


class RedisRateLimiter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.rules_ip: Dict[str, int] = settings.RATE_LIMIT_RULES_IP
        self.rules_path: Dict[str, int] = settings.RATE_LIMIT_RULES_PATH
        self.rules_ip_path: List[Dict[str, object]] = settings.RATE_LIMIT_RULES_IP_PATH

    @staticmethod
    def _window_id() -> int:
        return int(time.time() // 60)

    @staticmethod
    def _reset_in_seconds() -> int:
        now = time.time()
        return max(0, int(((int(now // 60) + 1) * 60) - now))

    def _match_rules(self, client_ip: str, path: str) -> List[Tuple[str, str, int]]:
        matched: List[Tuple[str, str, int]] = []
        if client_ip in self.rules_ip:
            matched.append(("ip", client_ip, int(self.rules_ip[client_ip])))
        for prefix, limit in self.rules_path.items():
            if path.startswith(prefix):
                matched.append(("path", prefix, int(limit)))
        for r in self.rules_ip_path:
            ip = str(r.get("ip", ""))
            prefix = str(r.get("path_prefix", ""))
            limit = int(r.get("limit", 0))
            if ip == client_ip and prefix and path.startswith(prefix):
                matched.append(("ippath", f"{ip}:{prefix}", limit))
        return matched

    @staticmethod
    def _key(scope: str, ident: str, window_id: int) -> str:
        return f"rl:{scope}:{ident}:{window_id}"

    async def check_and_increment(
        self, client_ip: str, path: str
    ) -> Tuple[bool, Optional[Tuple[str, str, int]], int, int]:
        window_id = self._window_id()
        rules = self._match_rules(client_ip, path)
        if not rules:
            return True, None, 0, 0

        r = await get_redis()
        pipe = r.pipeline()
        limits: List[int] = []

        for scope, ident, limit in rules:
            k = self._key(scope, ident, window_id)
            limits.append(limit)
            pipe.incr(k)
            pipe.expire(k, 60)

        results = await pipe.execute()
        counts = [int(results[i * 2]) for i in range(len(rules))]

        reset_in = self._reset_in_seconds()
        for idx, count in enumerate(counts):
            if count > limits[idx]:
                return False, rules[idx], max(0, limits[idx] - count), reset_in

        def spec_weight(scope: str) -> int:
            return 0 if scope == "ippath" else (1 if scope == "path" else 2)

        most_specific_idx = sorted(
            range(len(rules)), key=lambda i: spec_weight(rules[i][0])
        )[0]
        limit = limits[most_specific_idx]
        current = counts[most_specific_idx]
        remaining = max(0, limit - current)
        return True, rules[most_specific_idx], remaining, reset_in


_limiter: Optional[RedisRateLimiter] = None


def get_rate_limiter() -> RedisRateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RedisRateLimiter(Settings())
    return _limiter


async def rate_limit_middleware(request: Request, call_next: Callable) -> Response:
    limiter = get_rate_limiter()
    client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
        request.client.host if request.client else ""
    )
    path = request.url.path

    allowed, rule, remaining, reset_in = await limiter.check_and_increment(
        client_ip, path
    )
    if not allowed and rule is not None:
        scope, ident, limit = rule
        RATE_LIMIT_BLOCKED.labels(scope=scope).inc()
        headers = {
            "Retry-After": str(reset_in),
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
        }
        return JSONResponse(
            status_code=429,
            content={
                "error": "RATE_LIMIT_EXCEEDED",
                "message": "Too many requests",
                "details": {
                    "scope": scope,
                    "identifier": ident,
                    "reset_in": reset_in,
                },
            },
            headers=headers,
        )

    response: Response = await call_next(request)
    if rule is not None:
        scope, ident, limit = rule
        RATE_LIMIT_ALLOWED.labels(scope=scope).inc()
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_in)
    return response
