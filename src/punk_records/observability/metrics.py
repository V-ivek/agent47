from __future__ import annotations

from time import perf_counter

from fastapi import Request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

HTTP_REQUESTS_TOTAL = Counter(
    "punk_records_http_requests_total",
    "Total HTTP requests handled by Punk Records",
    ["method", "path", "status"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "punk_records_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
)

KAFKA_PRODUCED_EVENTS_TOTAL = Counter(
    "punk_records_kafka_produced_events_total",
    "Kafka events attempted by producer",
    ["topic", "result"],
)

KAFKA_CONSUMED_EVENTS_TOTAL = Counter(
    "punk_records_kafka_consumed_events_total",
    "Kafka messages processed by consumer loop",
    ["topic", "result"],
)


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


def _request_path_label(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None:
        path = getattr(route, "path", None)
        if isinstance(path, str) and path:
            return path
    return request.url.path or "unknown"


class RequestTimer:
    def __init__(self) -> None:
        self._start = perf_counter()

    def observe(self, request: Request, status_code: int | str) -> None:
        method = request.method.upper()
        path = _request_path_label(request)
        status = str(status_code)
        elapsed = perf_counter() - self._start

        HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=status).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(elapsed)


def observe_produced_event(*, topic: str, result: str) -> None:
    KAFKA_PRODUCED_EVENTS_TOTAL.labels(topic=topic, result=result).inc()


def observe_consumed_event(*, topic: str, result: str) -> None:
    KAFKA_CONSUMED_EVENTS_TOTAL.labels(topic=topic, result=result).inc()
