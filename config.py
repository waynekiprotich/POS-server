import os
import secrets
from datetime import timedelta

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _normalize_db_url(url: str) -> str:
    """Accept the postgres:// form some providers hand out."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _local_secret(name: str) -> str:
    """A secret from the environment, or one generated once and kept on disk.

    A shop installation should not need anyone to invent keys by hand. The file
    lives in instance/ (never committed) and is readable by the owner only.
    """
    value = os.getenv(name)
    if value:
        return value
    path = os.path.join(INSTANCE_DIR, "%s.key" % name.lower())
    try:
        with open(path) as handle:
            stored = handle.read().strip()
        if stored:
            return stored
    except FileNotFoundError:
        pass
    os.makedirs(INSTANCE_DIR, exist_ok=True)
    generated = secrets.token_hex(32)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(generated)
    return generated


class Config:
    # Anything other than development/testing is treated as production and must
    # not run with the placeholder secrets.
    PRODUCTION = os.getenv("FLASK_ENV", "production") not in ("development", "testing")
    # "local" = the shop's own computer with SQLite (the default).
    # "cloud" = a hosted server, which must use PostgreSQL.
    POS_MODE = os.getenv("POS_MODE", "local")

    SECRET_KEY = _local_secret("SECRET_KEY")
    JWT_SECRET_KEY = _local_secret("JWT_SECRET_KEY")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=int(os.getenv("JWT_ACCESS_MINUTES", "60"))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        days=int(os.getenv("JWT_REFRESH_DAYS", "30"))
    )

    SQLALCHEMY_DATABASE_URI = _normalize_db_url(
        os.getenv("DATABASE_URL", "sqlite:///" + os.path.join(INSTANCE_DIR, "pos.db"))
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    CORS_ORIGINS = [
        o.strip()
        for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
        if o.strip()
    ]

    LOGIN_RATE_LIMIT = int(os.getenv("LOGIN_RATE_LIMIT", "10"))
    LOGIN_RATE_WINDOW_SECONDS = int(os.getenv("LOGIN_RATE_WINDOW_SECONDS", "300"))
    # PINs are short, so they get a much tighter budget per account.
    PIN_ATTEMPT_LIMIT = int(os.getenv("PIN_ATTEMPT_LIMIT", "5"))

    # Number of reverse proxies in front of the app (1 on Render, 0 on a shop LAN).
    # Their X-Forwarded-For entry is trusted for the client address; anything the
    # client itself sends is not.
    TRUSTED_PROXY_COUNT = int(os.getenv("TRUSTED_PROXY_COUNT", "0"))

    # Default for the "timezone" setting; the owner can change it in Settings.
    BUSINESS_TIMEZONE = os.getenv("BUSINESS_TIMEZONE", "Africa/Nairobi")

    # The built React app. When present, Flask serves it so one process runs
    # the whole shop.
    FRONTEND_DIST = os.getenv(
        "FRONTEND_DIST", os.path.join(BASE_DIR, os.pardir, "client", "dist")
    )
    BACKUP_DIR = os.getenv("BACKUP_DIR", os.path.join(INSTANCE_DIR, "backups"))
    # Started by `run.py --lan`; off for tests, CLI commands and the dev server.
    BACKGROUND_JOBS = os.getenv("POS_BACKGROUND_JOBS") == "1"
    # Set to the address phones should open when auto-detection picks the wrong
    # network card, e.g. http://192.168.1.20:8080
    LAN_URL = os.getenv("LAN_URL", "")


class TestConfig(Config):
    TESTING = True
    PRODUCTION = False
    SECRET_KEY = "test-secret-key-" + "x" * 32
    JWT_SECRET_KEY = "test-jwt-secret-" + "x" * 32
    # Set TEST_DATABASE_URL to run the suite against PostgreSQL. The database is
    # dropped and recreated per test, so never point it at real data.
    SQLALCHEMY_DATABASE_URI = _normalize_db_url(os.getenv("TEST_DATABASE_URL", "sqlite://"))
    LOGIN_RATE_LIMIT = 1000
    PIN_ATTEMPT_LIMIT = 1000
    BACKGROUND_JOBS = False
    # Fast hashing for tests only; real installs use bcrypt's default cost of 12.
    BCRYPT_ROUNDS = 4
