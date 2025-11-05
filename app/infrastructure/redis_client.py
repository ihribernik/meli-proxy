from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Sequence
from redis.asyncio.cluster import ClusterNode

import redis.asyncio as redis

from app.core.config import Settings

_redis_client: redis.Redis | redis.RedisCluster | None = None


def _parse_cluster_nodes(nodes: str) -> Sequence[tuple[str, int]]:
    parsed: list[tuple[str, int]] = []
    for part in nodes.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            host, port_s = part.split(":", 1)
            try:
                parsed.append((host.strip(), int(port_s)))
            except ValueError:
                continue
        else:
            parsed.append((part, 6379))
    return parsed


async def _wait_ready(
    client: redis.Redis | redis.RedisCluster, retries: int, base_backoff: float
) -> None:
    """Wait until Redis/Cluster answers ping with exponential backoff."""
    attempt = 0
    while True:
        try:
            ping_result: bool | Awaitable[bool] = client.ping()
            ok = (
                await ping_result
                if isinstance(ping_result, Awaitable)
                else bool(ping_result)
            )

            if ok:
                return
        except Exception:
            pass
        attempt += 1
        if attempt > retries:
            raise RuntimeError("Redis not ready after retries")
        sleep = min(5.0, base_backoff * (2 ** (attempt - 1)))
        # add jitter +/- 20%
        jitter = sleep * (random.random() * 0.4 - 0.2)
        await asyncio.sleep(max(0.1, sleep + jitter))


async def get_redis() -> redis.Redis | redis.RedisCluster:
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    settings = Settings()
    if settings.REDIS_CLUSTER_NODES:
        startup_nodes = _parse_cluster_nodes(settings.REDIS_CLUSTER_NODES)
        _redis_client = redis.RedisCluster(
            startup_nodes=[ClusterNode(h, p) for h, p in startup_nodes],
            password=settings.REDIS_PASSWORD,
            decode_responses=False,
            read_from_replicas=True,
            # skip_full_coverage_check=True,
        )
    else:
        _redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            db=settings.REDIS_DB,
            decode_responses=False,
        )

    await _wait_ready(
        _redis_client, settings.REDIS_INIT_RETRIES, settings.REDIS_INIT_BACKOFF
    )
    return _redis_client
