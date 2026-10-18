
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("app.requests")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        start_time = time.perf_counter()

        try:
            response: Response = await call_next(request)

            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                "request_completed request_id=%s method=%s path=%s "
                "status_code=%s duration_ms=%.2f",
                request_id,
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )

            response.headers["X-Request-ID"] = request_id
            return response

        except Exception:
            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.exception(
                "request_failed request_id=%s method=%s path=%s "
                "duration_ms=%.2f",
                request_id,
                request.method,
                request.url.path,
                duration_ms,
            )
            raise
