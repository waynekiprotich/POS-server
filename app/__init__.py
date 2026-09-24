import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, jsonify, request, send_from_directory
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, OperationalError
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
    # Batch mode lets Alembic alter SQLite tables (it has no ALTER COLUMN).
    migrate.init_app(app, db, render_as_batch=True)
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
    _register_security_headers(app)
    _register_frontend(app)

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    if app.config.get("BACKGROUND_JOBS"):
        from .services.backup_service import start_scheduler

        start_scheduler(app)

    return app


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_connection, _record):
    """Make SQLite safe for several tills writing at once.

    WAL lets readers continue while a sale is being written, busy_timeout makes
    a second writer wait instead of failing, and foreign keys are off by default
    in SQLite.
    """
    if dbapi_connection.__class__.__module__.split(".")[0] not in ("sqlite3", "pysqlite2"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def _register_security_headers(app):
    @app.after_request
    def headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        # The phone scanner page needs the camera; nothing else does.
        response.headers.setdefault(
            "Permissions-Policy", "camera=(self), microphone=(), geolocation=()"
        )
        if request.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


def _register_frontend(app):
    """Serve the built React app so one process runs the whole shop."""
    dist = os.path.abspath(app.config.get("FRONTEND_DIST") or "")
    index = os.path.join(dist, "index.html")

    @app.get("/")
    @app.get("/<path:path>")
    def frontend(path=""):
        if path.startswith("api/") or path == "api":
            return jsonify({"error": "That endpoint does not exist."}), 404
        if not os.path.isfile(index):
            return (
                jsonify(
                    {
                        "error": "The POS screens have not been built yet. "
                        "Run ./setup.sh (or `npm run build:lan` in client/)."
                    }
                ),
                404,
            )
        candidate = os.path.join(dist, path)
        if path and os.path.isfile(candidate) and os.path.abspath(candidate).startswith(dist):
            response = send_from_directory(dist, path)
            if path.startswith("assets/"):
                # File names carry a content hash, so they never change.
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return response
        # Client-side routes (/pos, /scan/CODE, ...) all load the app shell.
        response = send_from_directory(dist, "index.html")
        response.headers["Cache-Control"] = "no-cache"
        return response


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
    cloud = config.get("POS_MODE") == "cloud"
    for key in ("SECRET_KEY", "JWT_SECRET_KEY"):
        value = config.get(key) or ""
        if value in WEAK_SECRETS or len(value) < MIN_SECRET_LENGTH:
            problems.append(
                "%s must be a random value of at least %d characters "
                '(python -c "import secrets; print(secrets.token_hex(32))").'
                % (key, MIN_SECRET_LENGTH)
            )
    if cloud and config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        problems.append(
            "DATABASE_URL must point at PostgreSQL when POS_MODE=cloud. SQLite on a "
            "hosted server is wiped on every deploy, taking the sales with it."
        )
    if problems:
        raise RuntimeError(
            "Production configuration is incomplete (set FLASK_ENV=development "
            "for local work):\n- " + "\n- ".join(problems)
        )

    if cloud and all("localhost" in o or "127.0.0.1" in o for o in config["CORS_ORIGINS"]):
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

    @app.errorhandler(OperationalError)
    def handle_database_unavailable(error):
        db.session.rollback()
        app.logger.exception("Database error")
        if app.testing:
            raise error
        return (
            jsonify(
                {
                    "error": "The database is busy or unavailable. Wait a moment and try "
                    "again; if it continues, restart the POS server."
                }
            ),
            503,
        )

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
