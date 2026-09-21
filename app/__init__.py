import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, jsonify
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from .extensions import cors, db, jwt, migrate
from .utils.errors import ApiError

WEAK_SECRETS = {"", "change-me", "dev-secret-change-me"}
MIN_SECRET_LENGTH = 32


def create_app(config_object=None):
    app = Flask(__name__)
    if config_object is None:
        from config import Config, TestConfig

        config_object = TestConfig if os.getenv("FLASK_ENV") == "testing" else Config
    app.config.from_object(config_object)
    _check_config(app)

    proxies = app.config.get("TRUSTED_PROXY_COUNT", 0)
    if proxies:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxies, x_proto=proxies)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        supports_credentials=True,
    )

    from . import models  # noqa: F401  (import so migrations see the tables)
    from .routes import BLUEPRINTS

    for blueprint in BLUEPRINTS:
        app.register_blueprint(blueprint)

    _register_error_handlers(app)
    _register_jwt_handlers(app)
    _register_cli(app)

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    return app


def _check_config(app):
    """Refuse to start with settings that would lose data or leak sessions."""
    config = app.config
    try:
        ZoneInfo(config["BUSINESS_TIMEZONE"])
    except (ZoneInfoNotFoundError, ValueError):
        raise RuntimeError(
            "BUSINESS_TIMEZONE '%s' is not a known timezone (e.g. Africa/Nairobi)."
            % config["BUSINESS_TIMEZONE"]
        )

    if not config.get("PRODUCTION"):
        return

    problems = []
    for key in ("SECRET_KEY", "JWT_SECRET_KEY"):
        value = config.get(key) or ""
        if value in WEAK_SECRETS or len(value) < MIN_SECRET_LENGTH:
            problems.append(
                "%s must be a random value of at least %d characters "
                '(python -c "import secrets; print(secrets.token_hex(32))").'
                % (key, MIN_SECRET_LENGTH)
            )
    if config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        problems.append(
            "DATABASE_URL must point at PostgreSQL. SQLite on a hosted server is "
            "wiped on every deploy, taking the sales with it."
        )
    if problems:
        raise RuntimeError(
            "Production configuration is incomplete (set FLASK_ENV=development "
            "for local work):\n- " + "\n- ".join(problems)
        )

    if all("localhost" in o or "127.0.0.1" in o for o in config["CORS_ORIGINS"]):
        app.logger.warning(
            "CORS_ORIGINS only lists local addresses; set it to the frontend URL."
        )


def _register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(error):
        db.session.rollback()
        return jsonify(error.to_dict()), error.status_code

    @app.errorhandler(IntegrityError)
    def handle_integrity_error(error):
        db.session.rollback()
        app.logger.warning("Integrity error: %s", error)
        return (
            jsonify({"error": "That change conflicts with existing data."}),
            409,
        )

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        return jsonify({"error": error.description}), error.code

    @app.errorhandler(Exception)
    def handle_unexpected(error):
        db.session.rollback()
        app.logger.exception("Unhandled error")
        if app.debug or app.testing:
            raise error
        return jsonify({"error": "The server could not complete that request."}), 500


def _register_jwt_handlers(app):
    @jwt.expired_token_loader
    def expired(_header, _payload):
        return jsonify({"error": "Your session has expired. Please sign in again."}), 401

    @jwt.invalid_token_loader
    def invalid(_reason):
        return jsonify({"error": "Your session is not valid. Please sign in again."}), 401

    @jwt.unauthorized_loader
    def missing(_reason):
        return jsonify({"error": "Sign in to continue."}), 401


def _register_cli(app):
    from .cli import register_cli

    register_cli(app)
