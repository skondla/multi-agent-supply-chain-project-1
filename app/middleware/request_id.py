"""
Request ID middleware for distributed tracing.
"""
import time
import uuid
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID and timing to each request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        start_time = time.time()

        # Bind request context for structured logging
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        response = await call_next(request)

        process_time_ms = int((time.time() - start_time) * 1000)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = str(process_time_ms)

        logger.info(
            "Request completed",
            status_code=response.status_code,
            process_time_ms=process_time_ms,
        )

        structlog.contextvars.clear_contextvars()
        return response
