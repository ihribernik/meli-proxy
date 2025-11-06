from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Sequence

import redis.asyncio as redis
from redis.asyncio.cluster import ClusterNode

from app.core.config import Settings


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


class _RedisClientSingleton:
    _client: redis.Redis | redis.RedisCluster | None = None
    _lock: asyncio.Lock | None = None

    @classmethod
    async def _create_client(cls) -> redis.Redis | redis.RedisCluster:
        settings = Settings()
        if settings.REDIS_CLUSTER_NODES:
            startup_nodes = _parse_cluster_nodes(settings.REDIS_CLUSTER_NODES)
            client: redis.Redis | redis.RedisCluster = redis.RedisCluster(
                startup_nodes=[ClusterNode(h, p) for h, p in startup_nodes],
                password=settings.REDIS_PASSWORD,
                decode_responses=False,
                read_from_replicas=True,
            )
        else:
            client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                db=settings.REDIS_DB,
                decode_responses=False,
            )

        await _wait_ready(
            client, settings.REDIS_INIT_RETRIES, settings.REDIS_INIT_BACKOFF
        )
        return client

    @classmethod
    async def get_client(cls) -> redis.Redis | redis.RedisCluster:
        if cls._client is not None:
            return cls._client

        if cls._lock is None:
            cls._lock = asyncio.Lock()

        async with cls._lock:
            if cls._client is not None:
                return cls._client
            cls._client = await cls._create_client()
            return cls._client


async def get_redis() -> redis.Redis | redis.RedisCluster:
    return await _RedisClientSingleton.get_client()
