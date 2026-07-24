import secrets
import time

from flask import Flask, g, request

from app.database_security import assert_runtime_database_role
from app.modules import enforce_tenant_access
from app.tenant_context import clear_tenant_context


def register_http_hooks(app: Flask) -> None:
    @app.before_request
    def set_request_context() -> None:
        g.request_id = request.headers.get("X-Request-ID") or secrets.token_hex(16)
        g.request_started = time.perf_counter()
        assert_runtime_database_role()
        return enforce_tenant_access(request.endpoint, request.blueprint)

    @app.after_request
    def apply_response_headers(response):
        duration_ms = max(1, round((time.perf_counter() - g.request_started) * 1000))
        if response.mimetype == "application/json":
            response.headers["Content-Type"] = "application/json; charset=utf-8"
        response.headers["X-Request-ID"] = g.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        )
        response.headers["Cache-Control"] = "no-store"
        app.logger.info(
            "HTTP request completed method=%s path=%s status=%s",
            request.method,
            request.path,
            response.status_code,
            extra={"duration_ms": duration_ms},
        )
        return response

    @app.teardown_request
    def clear_request_tenant_context(_error) -> None:
        clear_tenant_context()
