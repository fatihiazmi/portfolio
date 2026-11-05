"""Prometheus metrics. Spec section 7a.1, plan T20.

The metrics server listens on its own port (`METRICS_PORT`), never on the API port.
The tunnel routes only the API port, so `/metrics` stays on the LAN.

Metrics live in the default registry, once per process. Tests read deltas.
"""

import logging
import threading
import time
from wsgiref.simple_server import WSGIServer

from prometheus_client import Counter, Histogram, start_wsgi_server
from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = logging.getLogger("portfolio_api.metrics")

# Label for requests that match no route, such as a 404 or a request the admin gate blocks.
# The raw path is never a label value: it would create one series per scanned URL.
UNMATCHED = "other"

REQUESTS = Counter(
    "portfolio_http_requests",
    "HTTP requests by method, route template, and status code.",
    ["method", "route", "status"],
)
LATENCY = Histogram(
    "portfolio_http_request_duration_seconds",
    "Time from request start to the last response byte. Background tasks are excluded.",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
LEADS = Counter("portfolio_leads", "Leads stored by the contact form. Count only.")

CONTACT_ERROR_REASONS = ("not_configured", "turnstile_unavailable", "email_failed")
CONTACT_ERRORS = Counter(
    "portfolio_contact_errors",
    "Contact form errors on the server side. Rejected spam and bad input are not errors.",
    ["reason"],
)
# Create every series at 0, so `increase()` sees the first error.
for _reason in CONTACT_ERROR_REASONS:
    CONTACT_ERRORS.labels(_reason)


def contact_error(reason: str) -> None:
    CONTACT_ERRORS.labels(reason).inc()


def _route(scope: Scope) -> str:
    route = scope.get("route")
    return getattr(route, "path", None) or UNMATCHED


class MetricsMiddleware:
    """Counts requests and times them. Add it last, so it wraps every other middleware."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status = 500
        done = False

        def record() -> None:
            nonlocal done
            done = True
            method = scope["method"]
            route = _route(scope)
            REQUESTS.labels(method, route, str(status)).inc()
            LATENCY.labels(method, route).observe(time.perf_counter() - start)

        async def send_and_record(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                record()

        try:
            await self.app(scope, receive, send_and_record)
        finally:
            # An exception before the last body byte: count it as a 500.
            if not done:
                record()


def start_server(host: str, port: int) -> tuple[WSGIServer, threading.Thread]:
    server, thread = start_wsgi_server(port, addr=host)
    log.info("metrics on %s:%s/metrics", host, server.server_port)
    return server, thread
