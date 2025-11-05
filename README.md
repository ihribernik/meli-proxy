# Meli Proxy (FastAPI)

Proxy de alto rendimiento para la API de Mercado Libre, con rate limit distribuido en Redis y métricas Prometheus listas para Grafana.

## Características

- Proxy transparente a `https://api.mercadolibre.com` (sin redirect ni cache)
- Rate limiting por IP, por path y por IP+path en Redis/Redis Cluster
- Métricas Prometheus en `/metrics` (latencia, throughput, rate-limit)
- Docker Compose con Redis, Prometheus y Grafana
- Escalable horizontalmente (replicas)

## Variables de entorno (.env)

```env
HOST=0.0.0.0
PORT=8000
MELI_API_URL=https://api.mercadolibre.com

# Redis single
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0

# Redis cluster (alternativa)
# REDIS_CLUSTER_NODES=redis-node-0:6379,redis-node-1:6379,redis-node-2:6379

# Reglas rate limit (JSON)
RATE_LIMIT_RULES_IP_JSON={"152.152.152.152":1000}
RATE_LIMIT_RULES_PATH_JSON={"/categories/":10000}
RATE_LIMIT_RULES_IP_PATH_JSON=[{"ip":"152.152.152.152","path_prefix":"/items/","limit":10}]
```

## Ejecutar local

```bash
# Crear entorno virtual y activar
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
.venv\\Scripts\\Activate.ps1

# Instalar dependencias (dev)
pip install -r requirements-dev.txt

# Levantar la API
uvicorn app.fast_api:app --host 0.0.0.0 --port 8000

# Probar local
curl http://127.0.0.1:8000/health

# Probar vía Docker (mapea 8080->8000)
curl http://127.0.0.1:8080/categories/MLA97994
```

## Tests

```bash
# Opción simple
pytest

# Con tox (aislado por intérprete)
pip install tox
tox -e py311
```

## Docker Compose (Dev)

Servicios incluidos:

- `api`: FastAPI + /metrics
- `redis`: Redis 7 single node
- `prometheus`: scrape `/metrics` de `api`
- `grafana`: datasource Prometheus + dashboard básico

```bash
docker compose up --build -d
# escalar replicas (Compose):
docker compose up -d --scale api=3
```

Prometheus: [localhost:9090](http://localhost:9090)
Grafana: [localhost:3000](http://localhost:3000) (admin/admin)

## Endpoints

- `/health`: verifica conexión a Redis
- `/metrics`: métricas Prometheus
- `/*`: proxy a Mercado Libre (métodos GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS)

## Métricas expuestas

- Requests/latencias (instrumentación automática)
- `meli_proxy_rate_limit_allowed_total{scope}`
- `meli_proxy_rate_limit_blocked_total{scope}`

## Notas de rendimiento

- Use `--workers` en Uvicorn/Gunicorn para más CPU.
- Escale con `--scale api=N` y ponga un balanceador al frente.
- Redis Cluster recomendado en producción para sharding y disponibilidad.

## Perfiles de ejecución (Compose)

- Redis single node:
  - docker compose --profile single up --build -d
- Redis Cluster (recomendado para escalado):
  - export REDIS_CLUSTER_NODES=redis-cluster:7000,redis-cluster:7001,redis-cluster:7002,redis-cluster:7003,redis-cluster:7004,redis-cluster:7005
  - docker compose --profile cluster up --build -d

Escalar réplicas de la API:

- docker compose --profile single up -d --scale api=3
- docker compose --profile cluster up -d --scale api=3

### Inicialización de Redis (Backoff)

- `REDIS_INIT_RETRIES` (default: 30): reintentos de ping al iniciar
- `REDIS_INIT_BACKOFF` (default: 0.5): backoff inicial en segundos (exponencial con jitter)
