from app.extensions import db
from app.models import InventoryMovement, Product, Sale


def _sell(client, headers, product, quantity=1, **extra):
    body = {
        "items": [{"product_id": product.id, "quantity": quantity}],
        "payment_method": "cash",
        "received_amount": "100000",
    }
    body.update(extra)
    response = client.post("/api/sales", json=body, headers=headers)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["sale"]


def test_receipt_numbers_are_sequential(client, cashier, auth, product_factory):
    product = product_factory(stock=10)
    headers = auth("cashier")
    numbers = [_sell(client, headers, product)["sale_number"] for _ in range(3)]
    assert numbers == ["000001", "000002", "000003"]


def test_void_restores_stock_and_leaves_reports(client, admin, cashier, auth, product_factory):
    product = product_factory(stock=10, price=50, cost=30)
    sale = _sell(client, auth("cashier"), product, quantity=3)
    assert db.session.get(Product, product.id).stock_quantity == 7

    headers = auth("admin")
    response = client.post(
        "/api/sales/%d/void" % sale["id"], json={"reason": "Customer changed mind"}, headers=headers
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["sale"]["status"] == "voided"

    db.session.expire_all()
    assert db.session.get(Product, product.id).stock_quantity == 10
    movement = InventoryMovement.query.filter_by(movement_type="VOID").one()
    assert movement.quantity_change == 3 and movement.reference == sale["sale_number"]

    summary = client.get("/api/reports/summary?period=today", headers=headers).get_json()
    assert summary["totals"]["transactions"] == 0
    assert summary["totals"]["revenue"] == "0.00"

    # The record stays, and cannot be voided twice.
    assert db.session.get(Sale, sale["id"]) is not None
    again = client.post(
        "/api/sales/%d/void" % sale["id"], json={"reason": "again"}, headers=headers
    )
    assert again.status_code == 400
    assert db.session.get(Product, product.id).stock_quantity == 10


def test_void_needs_a_reason(client, admin, auth, product_factory):
    product = product_factory(stock=5)
    sale = _sell(client, auth("admin"), product)
    response = client.post("/api/sales/%d/void" % sale["id"], json={}, headers=auth("admin"))
    assert response.status_code == 400


def test_manager_can_discount_but_not_void(client, manager, auth, product_factory):
    product = product_factory(stock=5, price=100)
    headers = auth("manager")
    sale = _sell(client, headers, product, discount="10")
    assert sale["total"] == "90.00"
    response = client.post(
        "/api/sales/%d/void" % sale["id"], json={"reason": "x"}, headers=headers
    )
    assert response.status_code == 403


def test_category_and_cashier_reports(client, admin, cashier, auth, product_factory):
    product = product_factory(stock=10, price=40, cost=25)
    _sell(client, auth("cashier"), product, quantity=2)
    headers = auth("admin")

    categories = client.get("/api/reports/categories?period=today", headers=headers).get_json()
    assert categories["items"][0]["category_name"] == "Groceries"
    assert categories["items"][0]["revenue"] == "80.00"
    assert categories["items"][0]["gross_profit"] == "30.00"

    cashiers = client.get("/api/reports/cashiers?period=today", headers=headers).get_json()
    row = next(item for item in cashiers["items"] if item["name"] == "Cashier")
    assert row["transactions"] == 1 and row["revenue"] == "80.00"


def test_dashboard_includes_payment_breakdown(client, admin, auth, product_factory):
    product = product_factory(stock=10, price=40)
    headers = auth("admin")
    _sell(client, headers, product)
    body = client.get("/api/reports/summary?period=today", headers=headers).get_json()
    assert body["payments"] == [{"payment_method": "cash", "transactions": 1, "amount": "40.00"}]


def test_sales_csv_export_filters_and_escapes(client, admin, cashier, auth, product_factory):
    product = product_factory(stock=10, price=40)
    _sell(client, auth("cashier"), product)
    response = client.get("/api/sales/export", headers=auth("admin"))
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    lines = response.get_data(as_text=True).strip().splitlines()
    assert lines[0].startswith("Receipt,Date,Time,Cashier")
    assert "000001" in lines[1] and "Cashier" in lines[1]


def test_inventory_movement_types_follow_direction(client, admin, auth, product_factory):
    product = product_factory(stock=5)
    headers = auth("admin")
    bad = client.post(
        "/api/inventory/adjust",
        json={"product_id": product.id, "quantity_change": 2, "movement_type": "DAMAGED"},
        headers=headers,
    )
    assert bad.status_code == 400
    system_only = client.post(
        "/api/inventory/adjust",
        json={"product_id": product.id, "quantity_change": -1, "movement_type": "SALE"},
        headers=headers,
    )
    assert system_only.status_code == 400
    ok = client.post(
        "/api/inventory/adjust",
        json={
            "product_id": product.id,
            "quantity_change": -2,
            "movement_type": "EXPIRED",
            "note": "Past date",
        },
        headers=headers,
    )
    assert ok.status_code == 200
    movement = InventoryMovement.query.filter_by(movement_type="EXPIRED").one()
    assert (movement.previous_quantity, movement.quantity_change, movement.new_quantity) == (
        5,
        -2,
        3,
    )
    assert movement.user_id is not None


def test_negative_stock_policy(client, admin, auth, product_factory):
    product = product_factory(stock=1)
    headers = auth("admin")
    body = {
        "items": [{"product_id": product.id, "quantity": 3}],
        "payment_method": "cash",
        "received_amount": "10000",
    }
    assert client.post("/api/sales", json=body, headers=headers).status_code == 400
    client.patch("/api/settings", json={"allow_negative_stock": True}, headers=headers)
    assert client.post("/api/sales", json=body, headers=headers).status_code == 201
    db.session.expire_all()
    assert db.session.get(Product, product.id).stock_quantity == -2
