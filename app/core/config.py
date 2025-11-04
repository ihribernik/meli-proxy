from __future__ import annotations

import json
from typing import Any, Dict, List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.prod"),
        env_file_encoding="utf-8",
    )

    # API metadata
    API_TITLE: str = "Meli Proxy"
    API_VERSION: str = "1.0.0"
    HOST: str = "0.0.0.0"
    PORT: int = 8080
    DEBUG: bool = False

    # Upstream (Mercado Libre API)
    MELI_API_URL: str = "https://api.mercadolibre.com"

    # Backwards compatibility with existing proxy code
    @property
    def PROXY_UPSTREAM_BASE(self) -> str:
        return self.MELI_API_URL

    # CORS
    CORS_ORIGINS: List[str] = ["*"]

    # Redis / Redis Cluster
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str | None = None
    REDIS_DB: int = 0
    # Comma-separated list of host:port for cluster; when set, cluster mode is used
    REDIS_CLUSTER_NODES: str | None = None

    # Rate limiting defaults (per minute)
    RATE_LIMIT_DEFAULT: int = 0  # 0 = unlimited if no rule matches

    # Rules configured via JSON envs for flexibility
    RATE_LIMIT_RULES_IP_JSON: str | None = None
    RATE_LIMIT_RULES_PATH_JSON: str | None = None
    RATE_LIMIT_RULES_IP_PATH_JSON: str | None = None

    # Sensible defaults matching the challenge examples
    @property
    def RATE_LIMIT_RULES_IP(self) -> Dict[str, int]:
        if self.RATE_LIMIT_RULES_IP_JSON:
            try:
                data = json.loads(self.RATE_LIMIT_RULES_IP_JSON)
                return {str(k): int(v) for k, v in dict(data).items()}
            except Exception:
                pass
        return {"152.152.152.152": 1000}

    @property
    def RATE_LIMIT_RULES_PATH(self) -> Dict[str, int]:
        if self.RATE_LIMIT_RULES_PATH_JSON:
            try:
                data = json.loads(self.RATE_LIMIT_RULES_PATH_JSON)
                return {str(k): int(v) for k, v in dict(data).items()}
            except Exception:
                pass
        return {"/categories/": 10000}

    @property
    def RATE_LIMIT_RULES_IP_PATH(self) -> List[Dict[str, Any]]:
        if self.RATE_LIMIT_RULES_IP_PATH_JSON:
            try:
                data = json.loads(self.RATE_LIMIT_RULES_IP_PATH_JSON)
                if isinstance(data, list):
                    out: List[Dict[str, Any]] = []
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        ip = str(item.get("ip", "")).strip()
                        prefix = str(item.get("path_prefix", ""))
                        limit = int(item.get("limit", 0))
                        if ip and prefix and limit > 0:
                            out.append({"ip": ip, "path_prefix": prefix, "limit": limit})
                    if out:
                        return out
            except Exception:
                pass
        return [{"ip": "152.152.152.152", "path_prefix": "/items/", "limit": 10}]
