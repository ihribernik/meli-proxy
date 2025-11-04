# TODO - Proxy Meli

## Mejoras
- [ ] Añadir Redis Cluster en Compose (bitnami/redis-cluster) para pruebas de sharding
- [ ] Añadir redis-exporter para métricas de Redis en Prometheus
- [ ] Dashboard Grafana más completo (latency p50/p90/p99 por ruta, errores)
- [ ] Integrar reverse proxy (NGINX/Traefik) para balanceo externo
- [ ] K8s manifests (Deployment con replicas, Service, HPA por RPS y CPU)
- [ ] Cache opcional (TTL configurable) en el proxy para GETs
- [ ] Circuit breaker y timeouts finos por upstream

## Operación
- Escalado horizontal: `docker compose up -d --scale api=3`
- Prometheus scrape: `deploy/prometheus/prometheus.yml`
- Grafana datasource y dashboard: `deploy/grafana/provisioning/**`

## Tests
- [ ] Carga con k6/vegeta para validar >50k req/s en escenario multi-replica
- [ ] Tests de límites por IP, path y IP+path
- [ ] E2E básico de `/categories/MLA97994`
