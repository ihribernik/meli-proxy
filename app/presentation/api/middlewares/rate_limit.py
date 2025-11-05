from __future__ import annotations

import json
import time
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import Request, Response
from prometheus_client import Counter
from starlette.responses import JSONResponse

from app.core.config import Settings
from app.infrastructure.redis_client import get_redis

logger = logging.getLogger(__name__)

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
RATE_LIMIT_CONFIG_UPDATES = Counter(
    "meli_proxy_rate_limit_config_updates_total",
    "Number of times rate-limit configuration was updated",
)


class RedisRateLimiter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.rules_ip: Dict[str, int] = settings.RATE_LIMIT_RULES_IP
        self.rules_path: Dict[str, int] = settings.RATE_LIMIT_RULES_PATH
        self.rules_ip_path: List[Dict[str, object]] = settings.RATE_LIMIT_RULES_IP_PATH
        self._cache_ttl = max(1.0, float(settings.RATE_LIMIT_CACHE_SECONDS))
        self._last_refresh: float = 0.0
        self._updated_at: float | None = None

    _RULES_KEY_IP = "rl:config:rules_ip"
    _RULES_KEY_PATH = "rl:config:rules_path"
    _RULES_KEY_IP_PATH = "rl:config:rules_ip_path"
    _RULES_UPDATED_AT = "rl:config:updated_at"
    _EVENT_CHANNEL = "rl:config:events"

    @staticmethod
    def _normalize_ip_rules(data: Dict[str, Any]) -> Dict[str, int]:
        normalized: Dict[str, int] = {}
        for k, v in data.items():
            try:
                limit = int(v)
            except Exception:
                continue
            if limit > 0:
                normalized[str(k)] = limit
        return normalized

    @staticmethod
    def _normalize_path_rules(data: Dict[str, Any]) -> Dict[str, int]:
        normalized: Dict[str, int] = {}
        for k, v in data.items():
            try:
                limit = int(v)
            except Exception:
                continue
            if limit > 0:
                normalized[str(k)] = limit
        return normalized

    @staticmethod
    def _normalize_ip_path_rules(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            ip = str(item.get("ip", "")).strip()
            prefix = str(item.get("path_prefix", "")).strip()
            try:
                limit = int(item.get("limit", 0))
            except Exception:
                continue
            if ip and prefix and limit > 0:
                normalized.append({"ip": ip, "path_prefix": prefix, "limit": limit})
        return normalized

    async def _ensure_rules(self) -> None:
        now = time.time()
        if now - self._last_refresh < self._cache_ttl:
            return
        r = await get_redis()
        pipe = r.pipeline()
        pipe.get(self._RULES_KEY_IP)
        pipe.get(self._RULES_KEY_PATH)
        pipe.get(self._RULES_KEY_IP_PATH)
        pipe.get(self._RULES_UPDATED_AT)
        raw_ip, raw_path, raw_ip_path, raw_updated_at = await pipe.execute()

        defaults_ip = self.settings.RATE_LIMIT_RULES_IP
        defaults_path = self.settings.RATE_LIMIT_RULES_PATH
        defaults_ip_path = self.settings.RATE_LIMIT_RULES_IP_PATH

        ip_rules = defaults_ip
        path_rules = defaults_path
        ip_path_rules = defaults_ip_path

        if raw_ip:
            try:
                ip_rules = self._normalize_ip_rules(json.loads(raw_ip.decode()))
            except Exception:
                ip_rules = defaults_ip
        if raw_path:
            try:
                path_rules = self._normalize_path_rules(json.loads(raw_path.decode()))
            except Exception:
                path_rules = defaults_path
        if raw_ip_path:
            try:
                parsed = json.loads(raw_ip_path.decode())
                if isinstance(parsed, list):
                    ip_path_rules = self._normalize_ip_path_rules(parsed)
            except Exception:
                ip_path_rules = defaults_ip_path

        self.rules_ip = ip_rules
        self.rules_path = path_rules
        self.rules_ip_path = ip_path_rules
        updated_at: float | None = None
        if raw_updated_at:
            try:
                updated_at = float(raw_updated_at.decode())
            except Exception:
                updated_at = None
        self._updated_at = updated_at
        self._last_refresh = now

    async def set_rules(
        self,
        ip_rules: Dict[str, int],
        path_rules: Dict[str, int],
        ip_path_rules: List[Dict[str, Any]],
    ) -> None:
        normalized_ip = self._normalize_ip_rules(ip_rules)
        normalized_path = self._normalize_path_rules(path_rules)
        normalized_ip_path = self._normalize_ip_path_rules(ip_path_rules)

        payload_ip = json.dumps(normalized_ip, separators=(",", ":"))
        payload_path = json.dumps(normalized_path, separators=(",", ":"))
        payload_ip_path = json.dumps(normalized_ip_path, separators=(",", ":"))
        now = time.time()

        r = await get_redis()
        pipe = r.pipeline()
        pipe.set(self._RULES_KEY_IP, payload_ip)
        pipe.set(self._RULES_KEY_PATH, payload_path)
        pipe.set(self._RULES_KEY_IP_PATH, payload_ip_path)
        pipe.set(self._RULES_UPDATED_AT, str(now))
        await pipe.execute()

        event_payload = json.dumps(
            {
                "ts": now,
                "ip": normalized_ip,
                "path": normalized_path,
                "ip_path": normalized_ip_path,
            },
            separators=(",", ":"),
        )
        try:
            await r.publish(self._EVENT_CHANNEL, event_payload)
        except Exception:
            logger.debug("Failed to publish rate-limit update event", exc_info=True)

        self.rules_ip = normalized_ip
        self.rules_path = normalized_path
        self.rules_ip_path = normalized_ip_path
        self._updated_at = now
        self._last_refresh = time.time()
        RATE_LIMIT_CONFIG_UPDATES.inc()
        logger.info("Rate-limit rules updated", extra={"scope": "admin_api"})

    async def get_rules(self) -> Dict[str, Any]:
        await self._ensure_rules()
        return {
            "ip": self.rules_ip,
            "path": self.rules_path,
            "ip_path": self.rules_ip_path,
            "updated_at": self._updated_at,
        }

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
        await self._ensure_rules()
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
