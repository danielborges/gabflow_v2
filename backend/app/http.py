import secrets

from flask import Flask, g, request

from app.modules import enforce_tenant_access


def register_http_hooks(app: Flask) -> None:
    @app.before_request
    def set_request_context() -> None:
        g.request_id = request.headers.get("X-Request-ID") or secrets.token_hex(16)
        return enforce_tenant_access(request.endpoint, request.blueprint)

    @app.after_request
    def apply_response_headers(response):
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
        return response
