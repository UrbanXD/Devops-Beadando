from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
from time import perf_counter

from prometheus_client import Counter, Histogram, make_asgi_app


request_id_context: ContextVar[str | None] = ContextVar(
    "request_id",
    default=None,
)

HTTP_REQUESTS = Counter(
    "converter_http_requests",
    "Completed requests to registered API routes, excluding health checks.",
    ("method", "route", "status"),
)
HTTP_REQUEST_DURATION = Histogram(
    "converter_http_request_duration_seconds",
    "Time until the API has prepared an HTTP response, in seconds.",
    ("route",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 180),
)
CONVERSION_JOBS = Counter(
    "converter_conversion_jobs",
    "Completed conversion outcomes by direction and result.",
    ("direction", "result"),
)
CONVERSION_ATTEMPTS = Counter(
    "converter_conversion_attempts",
    "Valid conversion attempts started after input validation.",
    ("direction",),
)
CONVERSION_DURATION = Histogram(
    "converter_conversion_duration_seconds",
    "Conversion and result preparation duration, in seconds.",
    ("direction", "result"),
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 90, 120, 180),
)

for _direction in ("pdf-to-docx", "docx-to-pdf"):
    CONVERSION_ATTEMPTS.labels(_direction)
    for _result in ("success", "failure"):
        CONVERSION_JOBS.labels(_direction, _result)
        CONVERSION_DURATION.labels(_direction, _result)

metrics_app = make_asgi_app()

_EXCLUDED_API_ROUTES = {
    "/api/health",
    "/api/health/ready",
}
_KNOWN_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


def is_observed_api_route(route: str | None) -> bool:
    return bool(
        route
        and route.startswith("/api/")
        and route not in _EXCLUDED_API_ROUTES
    )


def record_http_request(
    *,
    method: str,
    route: str,
    status: int,
    duration_seconds: float,
) -> None:
    bounded_method = method if method in _KNOWN_METHODS else "OTHER"
    HTTP_REQUESTS.labels(bounded_method, route, str(status)).inc()
    HTTP_REQUEST_DURATION.labels(route).observe(duration_seconds)


def log_event(event: str, **fields: object) -> None:
    payload: dict[str, object] = {
        "timestamp": datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "service": "converter-api",
        "event": event,
        **fields,
    }
    request_id = request_id_context.get()
    if request_id is not None:
        payload["request_id"] = request_id
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)


@contextmanager
def measure_conversion(direction: str) -> Iterator[None]:
    started_at = perf_counter()
    CONVERSION_ATTEMPTS.labels(direction).inc()
    log_event("conversion_started", direction=direction)
    try:
        yield
    except Exception as error:
        duration_seconds = perf_counter() - started_at
        CONVERSION_JOBS.labels(direction, "failure").inc()
        CONVERSION_DURATION.labels(direction, "failure").observe(duration_seconds)
        log_event(
            "conversion_completed",
            direction=direction,
            result="failure",
            duration_ms=round(duration_seconds * 1000, 2),
            error_type=type(error).__name__,
        )
        raise
    else:
        duration_seconds = perf_counter() - started_at
        CONVERSION_JOBS.labels(direction, "success").inc()
        CONVERSION_DURATION.labels(direction, "success").observe(duration_seconds)
        log_event(
            "conversion_completed",
            direction=direction,
            result="success",
            duration_ms=round(duration_seconds * 1000, 2),
        )
