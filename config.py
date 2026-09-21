import os
from datetime import timedelta

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _normalize_db_url(url: str) -> str:
    """Accept the postgres:// form some providers hand out."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


class Config:
    # Anything other than development/testing is treated as production and must
    # have real secrets and a real database before the app will start.
    PRODUCTION = os.getenv("FLASK_ENV", "production") not in ("development", "testing")

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=int(os.getenv("JWT_ACCESS_MINUTES", "60"))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        days=int(os.getenv("JWT_REFRESH_DAYS", "30"))
    )

    SQLALCHEMY_DATABASE_URI = _normalize_db_url(
        os.getenv("DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "pos.db"))
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

    # Number of reverse proxies in front of the app (1 on Render). Their
    # X-Forwarded-For entry is trusted for the client address; anything the
    # client itself sends is not.
    TRUSTED_PROXY_COUNT = int(os.getenv("TRUSTED_PROXY_COUNT", "0"))

    # "Today", date filters and the daily trend follow the shop's clock, not UTC.
    BUSINESS_TIMEZONE = os.getenv("BUSINESS_TIMEZONE", "Africa/Nairobi")


class TestConfig(Config):
    TESTING = True
    PRODUCTION = False
    # Set TEST_DATABASE_URL to run the suite against PostgreSQL. The database is
    # dropped and recreated per test, so never point it at real data.
    SQLALCHEMY_DATABASE_URI = _normalize_db_url(os.getenv("TEST_DATABASE_URL", "sqlite://"))
    LOGIN_RATE_LIMIT = 1000
