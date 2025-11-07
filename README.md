# Meli Proxy (FastAPI)

Proxy de alto rendimiento para la API de Mercado Libre, con rate limit distribuido en Redis y métricas Prometheus listas para Grafana.

## Características

- Proxy transparente a `https://api.mercadolibre.com` (sin redirect ni cache)
- Rate limiting por IP, por path y por IP+path en Redis/Redis Cluster
- Propagación de contexto a upstream (`X-Forwarded-For/Host/Proto`)
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

# Tokens para API de administración (separados por coma)
ADMIN_API_TOKENS=super-secret-token
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
# Redis single node
docker compose --profile single up --build -d
# Redis Cluster (carga vars desde deploy/compose/cluster.env)
docker compose --env-file deploy/compose/cluster.env --profile cluster up --build -d
# escalar replicas (Compose):
docker compose up -d --scale api=3
```

`deploy/compose/cluster.env` define los nodos por defecto del cluster; ajuste ese archivo si cambia puertos o topología.

> Nota: la imagen de Redis Cluster es configurable con `REDIS_CLUSTER_IMAGE` (default `grokzen/redis-cluster:latest`). Si necesita fijar una versión puntual, defínala antes de ejecutar Compose (ej: `REDIS_CLUSTER_IMAGE=grokzen/redis-cluster:7.2.4 docker compose ...`).

Prometheus: [localhost:9090](http://localhost:9090)
Grafana: [localhost:3000](http://localhost:3000) (admin/admin)

## Endpoints

- `/health`: verifica conexión a Redis
- `/metrics`: métricas Prometheus
- `/*`: proxy a Mercado Libre (métodos GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS)
- `/admin/rate-limits`: API REST (protegida) para leer/actualizar límites

## Métricas expuestas

- Requests/latencias (instrumentación automática)
- `meli_proxy_rate_limit_allowed_total{scope}`
- `meli_proxy_rate_limit_blocked_total{scope}`
- `meli_proxy_rate_limit_config_updates_total`

## API de administración de rate limit

- Autenticación: encabezado `X-Admin-Token` con cualquiera de los valores definidos en `ADMIN_API_TOKENS`.
- Endpoints:
  - `GET /admin/rate-limits`: devuelve reglas vigentes (`ip`, `path`, `ip_path`, `updated_at`).
  - `PUT /admin/rate-limits`: reemplaza por completo las reglas.
  - `PATCH /admin/rate-limits`: modifica secciones puntuales.
  - `POST /admin/rate-limits/reset`: restablece valores por defecto.
- Eventos: cada actualización publica un mensaje JSON en el canal Redis `rl:config:events` (y actualiza `rl:config:updated_at`). Las réplicas solo consumen el hash/JSON, pero servicios externos pueden suscribirse a ese canal para auditar cambios.
- Seguridad: si no se define `ADMIN_API_TOKENS`, el endpoint queda deshabilitado y responde 403.

## Notas de rendimiento

- Use `--workers` en Uvicorn/Gunicorn para más CPU.
- Escale con `--scale api=N` y ponga un balanceador al frente.
- Redis Cluster recomendado en producción para sharding y disponibilidad.

## Pruebas de carga (Artillery)

- El perfil `deploy/load/artillery-50k.yml` rampa hasta ~50k req/s contra `/health`; puede parametrizar el destino con `TARGET_URL` y `TARGET_PATH`.
- Antes de ejecutar, levante la API (idealmente vía `docker compose up --build -d`) y aumente/relaje los límites en Redis usando la API de administración o variables `RATE_LIMIT_RULES_*`.
- Ejecución local típica:

```bash
TARGET_URL=http://127.0.0.1:8000 \
TARGET_PATH=/health \
artillery run deploy/load/artillery-50k.yml
```

- Artillery necesita Node.js (`npm install -g artillery`). Para llegar a 50k req/s, ejecute el generador en un host separado o use `artillery run --count 4` para lanzar varios workers.
- Monitoree `/metrics` (Prometheus/Grafana) durante la prueba para confirmar throughput real y detectar throttling (`meli_proxy_rate_limit_*`).

## Perfiles de ejecución (Compose)

- Redis single node:
  - docker compose --profile single up --build -d
- Redis Cluster (recomendado para escalado):
  - docker compose --env-file deploy/compose/cluster.env --profile cluster up --build -d

Escalar réplicas de la API:

- docker compose --profile single up -d --scale api=3
- docker compose --profile cluster up -d --scale api=3

### Inicialización de Redis (Backoff)

- `REDIS_INIT_RETRIES` (default: 30): reintentos de ping al iniciar
- `REDIS_INIT_BACKOFF` (default: 0.5): backoff inicial en segundos (exponencial con jitter)
