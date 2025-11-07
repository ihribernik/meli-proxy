from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import call, patch

from app.infrastructure import redis_client


class _FakeRedis:
    def __init__(self) -> None:
        self.ping_calls = 0

    async def ping(self) -> bool:
        self.ping_calls += 1
        return True


class RedisClientSingletonTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        redis_client._RedisClientSingleton._client = None
        redis_client._RedisClientSingleton._lock = None

    def tearDown(self) -> None:
        redis_client._RedisClientSingleton._client = None
        redis_client._RedisClientSingleton._lock = None

    async def test_get_redis_returns_singleton_instance(self) -> None:
        fake_client = _FakeRedis()
        fake_settings = SimpleNamespace(
            REDIS_CLUSTER_NODES=None,
            REDIS_PASSWORD=None,
            REDIS_HOST="localhost",
            REDIS_PORT=6379,
            REDIS_DB=0,
            REDIS_INIT_RETRIES=1,
            REDIS_INIT_BACKOFF=0.01,
        )

        with patch.object(redis_client, "Settings", return_value=fake_settings), patch(
            "app.infrastructure.redis_client.redis.Redis", return_value=fake_client
        ) as redis_ctor:
            first = await redis_client.get_redis()
            second = await redis_client.get_redis()

        self.assertIs(first, fake_client)
        self.assertIs(second, fake_client)
        self.assertEqual(redis_ctor.call_count, 1)
        self.assertGreaterEqual(fake_client.ping_calls, 1)

    async def test_cluster_configuration_builds_nodes_and_client(self) -> None:
        fake_client = _FakeRedis()
        fake_settings = SimpleNamespace(
            REDIS_CLUSTER_NODES="node1:7001,node2",
            REDIS_PASSWORD="secret",
            REDIS_HOST="localhost",
            REDIS_PORT=6379,
            REDIS_DB=0,
            REDIS_INIT_RETRIES=1,
            REDIS_INIT_BACKOFF=0.01,
        )

        with patch.object(redis_client, "Settings", return_value=fake_settings), patch(
            "app.infrastructure.redis_client.redis.RedisCluster",
            return_value=fake_client,
        ) as cluster_ctor, patch(
            "app.infrastructure.redis_client.ClusterNode"
        ) as cluster_node:
            cluster_node.side_effect = lambda host, port: (host, port)
            client = await redis_client.get_redis()

        self.assertIs(client, fake_client)
        cluster_ctor.assert_called_once()
        cluster_node.assert_has_calls(
            [call("node1", 7001), call("node2", 6379)],
            any_order=False,
        )
