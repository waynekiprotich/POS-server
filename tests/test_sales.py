from app.extensions import db
from app.models import InventoryMovement, Product


def test_full_sale_loop_reduces_stock_and_returns_receipt(
    client, cashier, auth, product_factory
):
    product = product_factory(stock=10, price=75, cost=58)
    headers = auth("cashier")

    response = client.post(
        "/api/sales",
        json={
            "items": [{"product_id": product.id, "quantity": 2}],
            "payment_method": "cash",
            "received_amount": "500",
        },
        headers=headers,
    )
    body = response.get_json()
    assert response.status_code == 201, body

    sale = body["sale"]
    assert sale["sale_number"] == "000001"
    assert sale["subtotal"] == "150.00"
    assert sale["total"] == "150.00"
    assert sale["payment"]["change_amount"] == "350.00"
    assert sale["items"][0]["unit_price"] == "75.00"
    assert body["business"]["currency"] == "KES"

    refreshed = db.session.get(Product, product.id)
    assert refreshed.stock_quantity == 8

    movement = InventoryMovement.query.filter_by(product_id=product.id).one()
    assert movement.movement_type == "SALE"
    assert movement.quantity_change == -2
    assert movement.new_quantity == 8


def test_sale_is_rejected_when_stock_is_short(client, cashier, auth, product_factory):
    product = product_factory(stock=2)
    response = client.post(
        "/api/sales",
        json={
            "items": [{"product_id": product.id, "quantity": 5}],
            "payment_method": "cash",
            "received_amount": "1000",
        },
        headers=auth("cashier"),
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == (
        "Unable to complete sale because Milk 500ml only has 2 pc available."
    )
    assert db.session.get(Product, product.id).stock_quantity == 2


def test_failed_sale_leaves_no_partial_records(client, cashier, auth, product_factory):
    ok_product = product_factory(name="Milk", sku="P001", barcode="1", stock=10)
    short_product = product_factory(name="Sugar", sku="P002", barcode="2", stock=1)

    response = client.post(
        "/api/sales",
        json={
            "items": [
                {"product_id": ok_product.id, "quantity": 1},
                {"product_id": short_product.id, "quantity": 4},
            ],
            "payment_method": "cash",
            "received_amount": "5000",
        },
        headers=auth("cashier"),
    )
    assert response.status_code == 400
    assert db.session.get(Product, ok_product.id).stock_quantity == 10
    assert InventoryMovement.query.count() == 0


def test_cash_must_cover_the_total(client, cashier, auth, product_factory):
    product = product_factory(stock=10, price=75)
    response = client.post(
        "/api/sales",
        json={
            "items": [{"product_id": product.id, "quantity": 2}],
            "payment_method": "cash",
            "received_amount": "100",
        },
        headers=auth("cashier"),
    )
    assert response.status_code == 400
    assert "less than the amount due" in response.get_json()["error"]


def test_mpesa_requires_a_reference(client, cashier, auth, product_factory):
    product = product_factory(stock=10)
    response = client.post(
        "/api/sales",
        json={
            "items": [{"product_id": product.id, "quantity": 1}],
            "payment_method": "mpesa",
        },
        headers=auth("cashier"),
    )
    assert response.status_code == 400
    assert response.get_json()["field"] == "reference"


def test_backend_ignores_prices_sent_by_the_client(client, cashier, auth, product_factory):
    product = product_factory(stock=10, price=75)
    body = client.post(
        "/api/sales",
        json={
            "items": [{"product_id": product.id, "quantity": 1, "unit_price": "1"}],
            "payment_method": "cash",
            "received_amount": "100",
            "total": "1",
        },
        headers=auth("cashier"),
    ).get_json()
    assert body["sale"]["total"] == "75.00"


def test_receipt_keeps_the_price_charged_at_the_time(client, admin, auth, product_factory):
    product = product_factory(stock=10, price=75)
    headers = auth("admin")
    sale_id = client.post(
        "/api/sales",
        json={
            "items": [{"product_id": product.id, "quantity": 1}],
            "payment_method": "cash",
            "received_amount": "100",
        },
        headers=headers,
    ).get_json()["sale"]["id"]

    client.patch("/api/products/%d" % product.id, json={"selling_price": "120"}, headers=headers)

    receipt = client.get("/api/sales/%d" % sale_id, headers=headers).get_json()
    assert receipt["sale"]["items"][0]["unit_price"] == "75.00"


def test_cashier_only_sees_own_sales(client, admin, cashier, auth, product_factory):
    product = product_factory(stock=10)
    client.post(
        "/api/sales",
        json={
            "items": [{"product_id": product.id, "quantity": 1}],
            "payment_method": "cash",
            "received_amount": "100",
        },
        headers=auth("admin"),
    )
    listed = client.get("/api/sales", headers=auth("cashier")).get_json()
    assert listed["items"] == []


def test_cashier_cannot_apply_a_discount(client, cashier, auth, product_factory):
    product = product_factory(stock=10)
    response = client.post(
        "/api/sales",
        json={
            "items": [{"product_id": product.id, "quantity": 1}],
            "payment_method": "cash",
            "received_amount": "100",
            "discount": "10",
        },
        headers=auth("cashier"),
    )
    assert response.status_code == 400
    assert "administrator" in response.get_json()["error"]
