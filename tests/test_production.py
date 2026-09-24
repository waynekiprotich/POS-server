from datetime import timedelta

import pytest

from app import create_app
from app.extensions import db
from app.models import Sale
from app.utils import dates
from config import TestConfig

STRONG = "x" * 40


def _config(**overrides):
    return type("Config", (TestConfig,), overrides)


def test_production_refuses_default_secrets():
    config = _config(
        PRODUCTION=True,
        SECRET_KEY="dev-secret-change-me",
        JWT_SECRET_KEY=STRONG,
        SQLALCHEMY_DATABASE_URI="postgresql+psycopg://u:p@db/pos",
    )
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app(config)


def test_cloud_mode_refuses_sqlite():
    config = _config(
        PRODUCTION=True,
        POS_MODE="cloud",
        SECRET_KEY=STRONG,
        JWT_SECRET_KEY=STRONG,
        SQLALCHEMY_DATABASE_URI="sqlite://",
    )
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        create_app(config)


def test_local_shop_mode_runs_on_sqlite():
    config = _config(
        PRODUCTION=True,
        POS_MODE="local",
        SECRET_KEY=STRONG,
        JWT_SECRET_KEY=STRONG,
        SQLALCHEMY_DATABASE_URI="sqlite://",
    )
    assert create_app(config) is not None


def test_production_starts_with_complete_config():
    config = _config(
        PRODUCTION=True,
        SECRET_KEY=STRONG,
        JWT_SECRET_KEY=STRONG,
        SQLALCHEMY_DATABASE_URI="postgresql+psycopg://u:p@db/pos",
    )
    assert create_app(config) is not None


def test_unknown_timezone_is_rejected():
    with pytest.raises(RuntimeError, match="BUSINESS_TIMEZONE"):
        create_app(_config(BUSINESS_TIMEZONE="Mars/Olympus"))


def test_spoofed_forwarded_for_cannot_dodge_login_limit():
    app = create_app(_config(LOGIN_RATE_LIMIT=2, TRUSTED_PROXY_COUNT=1))
    client = app.test_client()
    statuses = []
    with app.app_context():
        db.create_all()
        try:
            for n in range(3):
                # The proxy appends the real address; the client controls what precedes it.
                response = client.post(
                    "/api/auth/login",
                    json={"identifier": "nobody", "password": "wrong"},
                    headers={"X-Forwarded-For": "10.0.0.%d, 203.0.113.9" % n},
                )
                statuses.append(response.status_code)
        finally:
            db.session.remove()
            db.drop_all()
    assert statuses == [401, 401, 429]


def test_bad_query_filter_is_a_400(client, admin, auth):
    response = client.get("/api/sales?cashier_id=abc", headers=auth("admin"))
    assert response.status_code == 400


def test_non_finite_cash_amount_is_rejected(client, cashier, auth, product_factory):
    product = product_factory(stock=5)
    response = client.post(
        "/api/sales",
        json={
            "items": [{"product_id": product.id, "quantity": 1}],
            "payment_method": "cash",
            "received_amount": "NaN",
        },
        headers=auth("cashier"),
    )
    assert response.status_code == 400
    assert response.get_json()["field"] == "received_amount"


def test_non_finite_tax_rate_is_rejected(client, admin, auth):
    response = client.patch("/api/settings", json={"tax_rate": "nan"}, headers=auth("admin"))
    assert response.status_code == 400


def test_after_midnight_sale_counts_on_the_local_day(client, admin, auth, product_factory):
    product = product_factory(stock=10, price=100)
    headers = auth("admin")
    body = client.post(
        "/api/sales",
        json={
            "items": [{"product_id": product.id, "quantity": 1}],
            "payment_method": "cash",
            "received_amount": "100",
        },
        headers=headers,
    ).get_json()

    # 00:30 in Nairobi today is 21:30 UTC yesterday.
    today = dates.today()
    sale = db.session.get(Sale, body["sale"]["id"])
    sale.created_at = dates.day_start(today) + timedelta(minutes=30)
    db.session.commit()

    summary = client.get("/api/reports/summary?period=today", headers=headers).get_json()
    assert summary["totals"]["transactions"] == 1
    assert summary["trend"][-1] == {
        "date": today.isoformat(),
        "transactions": 1,
        "revenue": "100.00",
    }

    day = today.isoformat()
    listed = client.get(
        "/api/sales?start_date=%s&end_date=%s" % (day, day), headers=headers
    ).get_json()
    assert listed["pagination"]["total"] == 1
