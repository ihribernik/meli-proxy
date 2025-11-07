from __future__ import annotations

from typing import Dict, Iterable

import httpx
from fastapi import APIRouter, Request, Response

from app.core.config import Settings

router = APIRouter()


HOP_BY_HOP_HEADERS: set[str] = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def _filter_headers(headers: Iterable[tuple[str, str]]) -> Dict[str, str]:
    filtered: Dict[str, str] = {}
    for k, v in headers:
        lk = k.lower()
        if lk in HOP_BY_HOP_HEADERS:
            continue
        if lk == "host":
            continue
        filtered[k] = v
    return filtered


def _compose_forwarded_for(existing_chain: str, client_ip: str) -> str | None:
    if not client_ip:
        return None

    chain_parts = [
        part.strip() for part in existing_chain.split(",") if part and part.strip()
    ]
    if not chain_parts or chain_parts[-1] != client_ip:
        chain_parts.append(client_ip)

    if not chain_parts:
        return None

    return ", ".join(chain_parts)


class _ProxyAsyncClientSingleton:
    _client: httpx.AsyncClient | None = None

    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        if cls._client is None:
            cls._client = httpx.AsyncClient(
                follow_redirects=False,
                timeout=httpx.Timeout(10.0, connect=2.0),
                limits=httpx.Limits(
                    max_connections=2000,
                    max_keepalive_connections=2000,
                    keepalive_expiry=30.0,
                ),
            )
        return cls._client

    @classmethod
    def set_client(cls, client: httpx.AsyncClient | None) -> None:
        """Visible for tests to replace or clear the singleton instance."""
        cls._client = client


def _get_client() -> httpx.AsyncClient:
    return _ProxyAsyncClientSingleton.get_client()


@router.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    tags=["proxy"],
)
async def proxy_all(full_path: str, request: Request) -> Response:
    settings = Settings()
    upstream_base = settings.PROXY_UPSTREAM_BASE.rstrip("/")
    url = f"{upstream_base}/{full_path}"

    method = request.method
    headers = _filter_headers(request.headers.items())
    existing_forwarded_for = request.headers.get("x-forwarded-for", "")
    client_ip = existing_forwarded_for.split(",")[0].strip() or (
        request.client.host if request.client else ""
    )
    forwarded_for = _compose_forwarded_for(existing_forwarded_for, client_ip)
    if forwarded_for is not None:
        for key in list(headers.keys()):
            if key.lower() == "x-forwarded-for":
                headers.pop(key)
        headers["X-Forwarded-For"] = forwarded_for

    if request.headers.get("host") and not any(
        key.lower() == "x-forwarded-host" for key in headers
    ):
        headers["X-Forwarded-Host"] = request.headers["host"]

    if request.url.scheme and not any(
        key.lower() == "x-forwarded-proto" for key in headers
    ):
        headers["X-Forwarded-Proto"] = request.url.scheme

    body = await request.body()

    client = _get_client()
    upstream_resp = await client.request(
        method, url, headers=headers, params=request.query_params, content=body
    )

    resp_headers = _filter_headers(upstream_resp.headers.items())

    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        headers=resp_headers,
        media_type=upstream_resp.headers.get("content-type"),
    )
