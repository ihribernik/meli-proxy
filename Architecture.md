# Architecture Meli-Proxy

## Resumen
Proxy HTTP de alto rendimiento (FastAPI) hacia `https://api.mercadolibre.com`, con limitación de tasa distribuida en Redis (single o Cluster), métricas Prometheus y balanceo con Traefik.

## Diagrama (alto nivel)
```mermaid
flowchart LR
    C[Cliente] -->|HTTP| T[Traefik]
    subgraph Compose/K8s Cluster
      direction LR
      T --> A1[API Replica 1]
      T --> A2[API Replica 2]
      T --> A3[API Replica 3]
      subgraph Redis
        direction TB
        RC1[(Master 1)] --- RR1[(Replica 1)]
        RC2[(Master 2)] --- RR2[(Replica 2)]
        RC3[(Master 3)] --- RR3[(Replica 3)]
      end
    end
    A1 <-->|async| R[(Redis / Redis Cluster)]
    A2 <-->|async| R
    A3 <-->|async| R
    A1 -->|HTTP| U[(api.mercadolibre.com)]
    A2 -->|HTTP| U
    A3 -->|HTTP| U
```

## Flujo de Request
1. Traefik recibe el request y balancea a una réplica de la API.
2. Middleware de Rate Limit consulta/incrementa contadores en Redis por ventana de 60s (IP, Path, IP+Path).
3. Si excede límite → 429 con headers `Retry-After`, `X-RateLimit-*`.
4. Si pasa, el proxy reenvía hacia `api.mercadolibre.com` usando un `httpx.AsyncClient` compartido.
5. La respuesta se devuelve al cliente con headers filtrados.
6. Métricas: `/metrics` expone Prometheus (latencias/requests), y contadores de rate-limit (allowed/blocked).

## Componentes
- FastAPI App: `app/fast_api.py`
  - CORS, middleware de rate limit, rutas `/health`, `/metrics`, y proxy catch‑all.
- Proxy: `app/presentation/proxy.py`
  - Cliente `httpx` global con pool/keepalive para alto throughput.
- Rate Limit: `app/presentation/api/middlewares/rate_limit.py`
  - Claves por ventana: `rl:ip:{ip}:{window}`, `rl:path:{prefix}:{window}`, `rl:ippath:{ip}:{prefix}:{window}`.
  - Headers: `X-RateLimit-Limit/Remaining/Reset`.
  - Métricas: `meli_proxy_rate_limit_allowed_total`, `meli_proxy_rate_limit_blocked_total`.
- Redis Client: `app/infrastructure/redis_client.py`
  - Single o Cluster (auto por `REDIS_CLUSTER_NODES`), readiness con backoff.
- Observabilidad: Prometheus + Grafana (compose `deploy/*`).
- Balanceo: Traefik (compose) con labels en `api`.

## Variables relevantes
- `MELI_API_URL` (default: `https://api.mercadolibre.com`)
- Redis single: `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_DB`
- Redis cluster: `REDIS_CLUSTER_NODES` (lista host:port)
- Backoff Redis: `REDIS_INIT_RETRIES`, `REDIS_INIT_BACKOFF`
- Rate limit JSON: `RATE_LIMIT_RULES_IP_JSON`, `RATE_LIMIT_RULES_PATH_JSON`, `RATE_LIMIT_RULES_IP_PATH_JSON`

## Perfiles/Despliegue
- Compose perfiles: `single` y `cluster` (ver README)
- Escalado: `--scale api=3` (Traefik balancea), o K8s con Deployment + Service + HPA.
