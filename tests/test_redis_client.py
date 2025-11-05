import unittest

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.fast_api import app


class TestRedisClient(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.monkeypatch = MonkeyPatch()
