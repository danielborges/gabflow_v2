import sentry_sdk
from flask import Flask, jsonify
from sentry_sdk.integrations.flask import FlaskIntegration

from app.config import Config
from app.extensions import db, jwt, limiter, migrate
from app.http import register_http_hooks


def create_app(config_object: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)
    app.json.ensure_ascii = False

    _init_sentry(app)
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    limiter.init_app(app)
    register_http_hooks(app)

    from app.admin.routes import admin_bp
    from app.auth.routes import auth_bp
    from app.cli import register_commands
    from app.communications.routes import communications_bp
    from app.directory.routes import directory_bp
    from app.health.routes import health_bp
    from app.notifications.routes import notifications_bp
    from app.operations.routes import operations_bp, public_bp
    from app.privacy.routes import privacy_bp
    from app.requests.operations import request_ops_bp
    from app.requests.routes import requests_bp

    register_commands(app)
    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")
    app.register_blueprint(health_bp, url_prefix="/api/v1")
    app.register_blueprint(requests_bp, url_prefix="/api/v1")
    app.register_blueprint(communications_bp, url_prefix="/api/v1")
    app.register_blueprint(request_ops_bp, url_prefix="/api/v1")
    app.register_blueprint(directory_bp, url_prefix="/api/v1")
    app.register_blueprint(admin_bp, url_prefix="/api/v1/admin")
    app.register_blueprint(notifications_bp, url_prefix="/api/v1")
    app.register_blueprint(operations_bp, url_prefix="/api/v1")
    app.register_blueprint(privacy_bp, url_prefix="/api/v1")
    app.register_blueprint(public_bp, url_prefix="/api/v1")

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify(error="resource_not_found", message="Recurso não encontrado."), 404

    @app.errorhandler(429)
    def rate_limited(_error):
        return (
            jsonify(
                error="rate_limit_exceeded",
                message="Muitas tentativas. Aguarde antes de tentar novamente.",
            ),
            429,
        )

    return app


def _init_sentry(app: Flask) -> None:
    dsn = app.config.get("SENTRY_DSN")
    if not dsn:
        return

    sentry_sdk.init(
        dsn=dsn,
        environment=app.config["APP_ENV"],
        release=app.config.get("APP_RELEASE"),
        integrations=[FlaskIntegration()],
        traces_sample_rate=app.config["SENTRY_TRACES_SAMPLE_RATE"],
        send_default_pii=False,
    )
