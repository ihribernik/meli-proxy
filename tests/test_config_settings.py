from __future__ import annotations

import unittest

from app.core.config import Settings


class SettingsParsingTest(unittest.TestCase):
    def test_rate_limit_rules_ip_json_parsed(self) -> None:
        settings = Settings(
            RATE_LIMIT_RULES_IP_JSON='{"10.0.0.1": 15, "10.0.0.2": "20"}',
        )

        self.assertEqual(settings.RATE_LIMIT_RULES_IP, {"10.0.0.1": 15, "10.0.0.2": 20})

    def test_rate_limit_rules_ip_json_invalid_fallback(self) -> None:
        settings = Settings(RATE_LIMIT_RULES_IP_JSON="not-json")

        self.assertEqual(settings.RATE_LIMIT_RULES_IP, {"152.152.152.152": 1000})

    def test_rate_limit_rules_path_json_parsed(self) -> None:
        settings = Settings(RATE_LIMIT_RULES_PATH_JSON='{"a": 1, "/items/": "3"}')

        self.assertEqual(settings.RATE_LIMIT_RULES_PATH, {"a": 1, "/items/": 3})

    def test_rate_limit_rules_path_json_invalid_fallback(self) -> None:
        settings = Settings(RATE_LIMIT_RULES_PATH_JSON='{"a": "invalid"}')

        self.assertEqual(settings.RATE_LIMIT_RULES_PATH, {"/categories/": 10000})

    def test_rate_limit_rules_ip_path_json_filtered_entries(self) -> None:
        settings = Settings(
            RATE_LIMIT_RULES_IP_PATH_JSON="""
            [
                {"ip": "1.1.1.1", "path_prefix": "/items/", "limit": 10},
                {"ip": "   2.2.2.2   ", "path_prefix": "/categories/", "limit": "5"},
                {"ip": "", "path_prefix": "/items/", "limit": 10},
                {"ip": "3.3.3.3", "path_prefix": "", "limit": 10},
                {"ip": "4.4.4.4", "path_prefix": "/items/", "limit": 0}
            ]
            """,
        )

        self.assertEqual(
            settings.RATE_LIMIT_RULES_IP_PATH,
            [
                {"ip": "1.1.1.1", "path_prefix": "/items/", "limit": 10},
                {"ip": "2.2.2.2", "path_prefix": "/categories/", "limit": 5},
            ],
        )

    def test_rate_limit_rules_ip_path_json_non_list_fallback(self) -> None:
        settings = Settings(RATE_LIMIT_RULES_IP_PATH_JSON='{"not": "a list"}')

        self.assertEqual(
            settings.RATE_LIMIT_RULES_IP_PATH,
            [{"ip": "152.152.152.152", "path_prefix": "/items/", "limit": 10}],
        )

    def test_rate_limit_rules_ip_path_json_invalid_entries_fallback(self) -> None:
        settings = Settings(
            RATE_LIMIT_RULES_IP_PATH_JSON="""
            [
                "not a dict",
                {"ip": "", "path_prefix": "/items/", "limit": 10},
                {"ip": "1.1.1.1", "path_prefix": "/items/", "limit": "not-int"}
            ]
            """
        )

        self.assertEqual(
            settings.RATE_LIMIT_RULES_IP_PATH,
            [{"ip": "152.152.152.152", "path_prefix": "/items/", "limit": 10}],
        )

    def test_rate_limit_rules_ip_path_json_only_filtered_fallback(self) -> None:
        settings = Settings(
            RATE_LIMIT_RULES_IP_PATH_JSON="""
            [
                {"ip": "", "path_prefix": "/items/", "limit": 5},
                {"ip": "1.1.1.1", "path_prefix": "", "limit": 5},
                {"ip": "1.1.1.1", "path_prefix": "/items/", "limit": 0}
            ]
            """
        )

        self.assertEqual(
            settings.RATE_LIMIT_RULES_IP_PATH,
            [{"ip": "152.152.152.152", "path_prefix": "/items/", "limit": 10}],
        )

    def test_admin_api_keys_splits_and_strips(self) -> None:
        settings = Settings(ADMIN_API_TOKENS="foo, bar , ,baz,,")

        self.assertEqual(settings.ADMIN_API_KEYS, ["foo", "bar", "baz"])

    def test_admin_api_keys_empty(self) -> None:
        settings = Settings()
        self.assertEqual(settings.ADMIN_API_KEYS, [])

    def test_proxy_upstream_base_returns_meli_url(self) -> None:
        settings = Settings(MELI_API_URL="https://example.com")

        self.assertEqual(settings.PROXY_UPSTREAM_BASE, "https://example.com")


if __name__ == "__main__":
    unittest.main()
