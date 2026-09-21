from app.extensions import db
from app.models import Product, Setting


def test_restock_records_a_movement(client, admin, auth, product_factory):
    product = product_factory(stock=20)
    response = client.post(
        "/api/inventory/adjust",
        json={"product_id": product.id, "quantity_change": 12, "movement_type": "RESTOCK"},
        headers=auth("admin"),
    )
    assert response.status_code == 200
    assert response.get_json()["product"]["stock_quantity"] == 32

    movements = client.get("/api/inventory/movements", headers=auth("admin")).get_json()
    assert movements["items"][0]["previous_quantity"] == 20
    assert movements["items"][0]["new_quantity"] == 32


def test_adjustment_cannot_push_stock_negative(client, admin, auth, product_factory):
    product = product_factory(stock=3)
    response = client.post(
        "/api/inventory/adjust",
        json={"product_id": product.id, "quantity_change": -5, "movement_type": "DAMAGED"},
        headers=auth("admin"),
    )
    assert response.status_code == 400
    assert db.session.get(Product, product.id).stock_quantity == 3


def test_stock_status_thresholds(product_factory):
    product = product_factory(stock=0)
    assert product.stock_status == "out_of_stock"
    product.stock_quantity = 5
    assert product.stock_status == "low_stock"
    product.stock_quantity = 6
    assert product.stock_status == "in_stock"


def test_cashier_cannot_reach_reports(client, cashier, auth):
    assert client.get("/api/reports/summary", headers=auth("cashier")).status_code == 403


def test_summary_reports_revenue_and_profit(client, admin, auth, product_factory):
    product = product_factory(stock=10, cost=58, price=75)
    client.post(
        "/api/sales",
        json={
            "items": [{"product_id": product.id, "quantity": 2}],
            "payment_method": "cash",
            "received_amount": "500",
        },
        headers=auth("admin"),
    )
    body = client.get("/api/reports/summary?period=today", headers=auth("admin")).get_json()
    assert body["totals"]["revenue"] == "150.00"
    assert body["totals"]["cost_of_goods"] == "116.00"
    assert body["totals"]["gross_profit"] == "34.00"
    assert body["totals"]["transactions"] == 1
    assert body["top_products"][0]["units_sold"] == 2
    assert len(body["trend"]) == 7


def test_tax_setting_is_applied_by_the_backend(client, admin, auth, product_factory):
    product = product_factory(stock=10, price=100)
    headers = auth("admin")
    client.patch("/api/settings", json={"tax_enabled": True, "tax_rate": "16"}, headers=headers)
    body = client.post(
        "/api/sales",
        json={
            "items": [{"product_id": product.id, "quantity": 1}],
            "payment_method": "cash",
            "received_amount": "200",
        },
        headers=headers,
    ).get_json()
    assert body["sale"]["tax"] == "16.00"
    assert body["sale"]["total"] == "116.00"


def test_settings_reject_unknown_keys(client, admin, auth):
    response = client.patch("/api/settings", json={"nonsense": "1"}, headers=auth("admin"))
    assert response.status_code == 400
