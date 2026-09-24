import pytest

CASHIER_FORBIDDEN = [
    ("get", "/api/reports/summary"),
    ("get", "/api/reports/cashiers"),
    ("get", "/api/inventory"),
    ("get", "/api/inventory/movements"),
    ("post", "/api/inventory/adjust"),
    ("post", "/api/products"),
    ("post", "/api/categories"),
    ("patch", "/api/settings"),
    ("get", "/api/users"),
    ("get", "/api/users/activity"),
    ("get", "/api/backups"),
    ("post", "/api/backups"),
    ("post", "/api/sales/1/void"),
]


@pytest.mark.parametrize("method,path", CASHIER_FORBIDDEN)
def test_cashier_is_blocked_from_admin_apis(client, cashier, auth, method, path):
    response = getattr(client, method)(path, json={}, headers=auth("cashier"))
    assert response.status_code == 403, (path, response.get_json())


def test_cashier_does_not_receive_cost_prices(client, cashier, auth, product_factory):
    product_factory(cost=58, price=75)
    item = client.get("/api/products", headers=auth("cashier")).get_json()["items"][0]
    assert "cost_price" not in item and "margin" not in item


def test_cashier_receipt_has_no_costs(client, cashier, auth, product_factory):
    product = product_factory(stock=5, cost=58, price=75)
    body = client.post(
        "/api/sales",
        json={
            "items": [{"product_id": product.id, "quantity": 1}],
            "payment_method": "cash",
            "received_amount": "75",
        },
        headers=auth("cashier"),
    ).get_json()
    assert "gross_profit" not in body["sale"]
    assert "cost_price" not in body["sale"]["items"][0]


def test_cashier_sees_only_own_sales(client, admin, cashier, auth, product_factory):
    product = product_factory(stock=10, price=10)
    sale = {
        "items": [{"product_id": product.id, "quantity": 1}],
        "payment_method": "cash",
        "received_amount": "10",
    }
    admin_sale = client.post("/api/sales", json=sale, headers=auth("admin")).get_json()
    client.post("/api/sales", json=sale, headers=auth("cashier"))
    listed = client.get("/api/sales", headers=auth("cashier")).get_json()
    assert listed["pagination"]["total"] == 1
    other = client.get("/api/sales/%d" % admin_sale["sale"]["id"], headers=auth("cashier"))
    assert other.status_code == 403


def test_viewer_reads_reports_but_cannot_sell_or_change(client, viewer, auth, product_factory):
    product = product_factory(stock=5)
    headers = auth("viewer")
    assert client.get("/api/reports/summary", headers=headers).status_code == 200
    assert client.get("/api/sales", headers=headers).status_code == 200
    sale = client.post(
        "/api/sales",
        json={
            "items": [{"product_id": product.id, "quantity": 1}],
            "payment_method": "cash",
            "received_amount": "100",
        },
        headers=headers,
    )
    assert sale.status_code == 403
    assert client.post("/api/products", json={"name": "X"}, headers=headers).status_code == 403
    assert client.patch("/api/settings", json={}, headers=headers).status_code == 403


def test_manager_runs_inventory_but_not_settings_or_backups(
    client, manager, auth, product_factory
):
    product = product_factory(stock=5)
    headers = auth("manager")
    adjust = client.post(
        "/api/inventory/adjust",
        json={"product_id": product.id, "quantity_change": 3, "movement_type": "RESTOCK"},
        headers=headers,
    )
    assert adjust.status_code == 200
    assert client.get("/api/reports/summary", headers=headers).status_code == 200
    assert client.patch("/api/settings", json={"tax_rate": "1"}, headers=headers).status_code == 403
    assert client.get("/api/backups", headers=headers).status_code == 403


def test_role_comes_from_database_not_token(client, admin, cashier, auth):
    from app.extensions import db

    headers = auth("cashier")
    cashier.role = "admin"
    db.session.commit()
    # Same token, but the account was promoted: access follows the database.
    assert client.get("/api/users", headers=headers).status_code == 200
    cashier.role = "cashier"
    db.session.commit()
    assert client.get("/api/users", headers=headers).status_code == 403


def test_forged_token_is_rejected(client):
    import jwt

    token = jwt.encode({"sub": "1", "type": "access"}, "a-completely-different-secret-key-0123456789", algorithm="HS256")
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer %s" % token})
    assert response.status_code == 401
