# Architecture Meli-Proxy

## Descripción del Proyecto

Este proyecto es una versión optimizada en Python del proxy de Mercado Libre, desarrollada con FastAPI. Está diseñada para manejar **50,000+ requests por segundo**.

### Características Principales

- **Alto Rendimiento**: Arquitectura asíncrona con async/await
- **Escalabilidad Horizontal**: Diseñado para múltiples instancias
- **Rate Limiting Inteligente**: Por IP y por IP+path con autenticación
- **Caché Optimizado**: Redis con TTL configurable
- **Monitoreo**: Estadísticas detalladas de requests
- **Autenticación**: JWT tokens y API keys
- **Docker Ready**: Containerizado para despliegue fácil

### arquitectura

```

```

### Variables de Entorno (.env)

```env
# Servidor
HOST=0.0.0.0
PORT=8900

# API de Mercado Libre
MELI_API_URL=https://api.mercadolibre.com

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0

# Rate Limiting
RATE_LIMIT_GENERAL=5
RATE_LIMIT_PATH=3
RATE_LIMIT_AUTH=1000
RATE_LIMIT_AUTH_PATH=1000

# Seguridad
APP_KEY=very-hard-app-key
APP_ID=very-hard-app-id
JWT_TOKEN=jwt-token-validation

# Caché
CACHE_TTL_SECONDS=3600
```

### Autenticación

El sistema soporta dos métodos de autenticación:

1. **API Keys**: Headers `app-key` y `app-id`
2. **JWT Token**: Header `Authorization: Bearer <token>`

Los usuarios autenticados tienen límites de rate limiting más altos.

### 🏛️ Arquitectura Técnica

#### Componentes Principales

##### 1. FastAPI Application (main.py)

- Punto de entrada principal
- Configuración de rutas y middleware
- Manejo de CORS y eventos de ciclo de vida

##### 2. Rate Limiting Middleware (middleware/rate_limit.py)

- Controla límites por IP y por IP+path
- Cache local para reducir hits a Redis
- Diferenciación entre usuarios autenticados y no autenticados

##### 3. Servicios de Negocio

**MeliService (services/meli_service.py):**

- Proxy a la API de Mercado Libre
- Gestión de caché Redis
- Manejo de diferentes métodos HTTP

**StatisticsService (services/statistics_service.py):**

- Registro de métricas de requests
- Almacenamiento en Redis con TTL

##### 4. Repositorio Redis (repositories/redis_repo.py)

- Operaciones asíncronas con Redis
- Gestión de caché y contadores
- Manejo de expiración automática

##### 5. Modelos de Datos (models/)

- **ApiResponse**: Estructura de respuesta de la API
- **Statistics**: Métricas de requests
- **Tracking**: Seguimiento de rate limiting

#### Flujo de Request

```text
1. Request llega → Rate Limiting Middleware
2. Verificación de límites → Redis/Local Cache
3. Si válido → MeliService
4. Check Cache → Redis
5. Si no cacheado → Request a Meli API
6. Cache response → Redis
7. Log statistics → Redis
8. Return response
```
