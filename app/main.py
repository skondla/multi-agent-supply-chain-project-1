"""
Supply Chain AI Platform - FastAPI Application Entry Point
Multi-agent orchestration with Claude Opus 4.6
"""
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import settings
from app.core.database import init_db, close_db
from app.core.redis_client import init_redis, close_redis
from app.core.kafka_client import init_kafka, close_kafka
from app.core.logging import setup_logging
from app.middleware.security import SecurityHeadersMiddleware
from app.middleware.request_id import RequestIDMiddleware

# Setup logging before anything else
setup_logging()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    logger.info(
        "Starting Supply Chain AI Platform",
        version=settings.APP_VERSION,
        environment=settings.APP_ENV,
    )

    # Initialize connections
    await init_db()
    await init_redis()
    await init_kafka()

    logger.info("All services initialized successfully")
    yield

    # Cleanup
    logger.info("Shutting down Supply Chain AI Platform")
    await close_kafka()
    await close_redis()
    await close_db()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Supply Chain AI Platform",
    description="""
## Multi-Agent AI-Powered Supply Chain Orchestration

This platform provides intelligent supply chain management through specialized AI agents:

- **Orchestrator Agent**: Central coordinator for multi-agent workflows
- **Inventory Agent**: Real-time stock management and reordering
- **Order Agent**: Order validation, processing, and fraud detection
- **Supplier Agent**: Vendor evaluation and performance management
- **Logistics Agent**: Carrier selection and shipment optimization
- **Demand Forecast Agent**: ML-powered demand prediction
- **Anomaly Detection Agent**: Real-time anomaly and fraud detection

### Authentication
All endpoints (except `/health`, `/ready`, `/metrics`) require JWT Bearer tokens.
Obtain tokens via `POST /api/v1/auth/token`.
    """,
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
    contact={
        "name": "Supply Chain AI Team",
        "email": "api@supply-chain.ai",
    },
    license_info={
        "name": "Proprietary",
    },
)

# ── Middleware ────────────────────────────────────────────────────────────────

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Process-Time"],
)

# ── Metrics ───────────────────────────────────────────────────────────────────

Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    should_respect_env_var=False,
    should_instrument_requests_inprogress=True,
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

# ── Routers ───────────────────────────────────────────────────────────────────

from app.api.v1.router import api_router  # noqa: E402

app.include_router(api_router, prefix="/api/v1")

# ── Core Endpoints ────────────────────────────────────────────────────────────


@app.get("/health", tags=["health"], summary="Liveness probe")
async def health_check():
    """Kubernetes liveness probe."""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
    }


@app.get("/ready", tags=["health"], summary="Readiness probe")
async def readiness_check():
    """Kubernetes readiness probe - checks all dependencies."""
    from app.core.database import check_db_health
    from app.core.redis_client import check_redis_health
    from app.core.kafka_client import check_kafka_health

    db_ok = await check_db_health()
    redis_ok = await check_redis_health()
    kafka_ok = await check_kafka_health()

    all_healthy = db_ok and redis_ok
    return JSONResponse(
        status_code=status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "ready" if all_healthy else "not_ready",
            "checks": {
                "database": "ok" if db_ok else "failed",
                "redis": "ok" if redis_ok else "failed",
                "kafka": "ok" if kafka_ok else "not_available",
            },
        },
    )


# ── Exception Handlers ────────────────────────────────────────────────────────


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all exception handler."""
    logger.error(
        "Unhandled exception",
        error=str(exc),
        path=str(request.url.path),
        method=request.method,
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please try again later."},
    )
