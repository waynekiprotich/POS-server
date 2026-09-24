"""Barcode scanning: the scanner only supplies a barcode; the server supplies the rest."""
from app.extensions import db
from app.models import Product


def test_cashier_scan_lookup_returns_price_but_no_cost(client, cashier, auth, product_factory):
    product_factory(barcode="6161101234567", cost=55, price=80)
    body = client.get("/api/products/barcode/6161101234567", headers=auth("cashier")).get_json()
    assert body["found"] is True
    assert body["product"]["selling_price"] == "80.00"
    assert "cost_price" not in body["product"]


def test_unknown_barcode_is_a_clear_404(client, cashier, auth):
    response = client.get("/api/products/barcode/0000000000000", headers=auth("cashier"))
    assert response.status_code == 404
    assert response.get_json() == {"found": False, "barcode": "0000000000000"}


def test_archived_product_cannot_be_scanned(client, cashier, auth, product_factory):
    product = product_factory(barcode="6161101234567")
    product.is_active = False
    db.session.commit()
    response = client.get("/api/products/barcode/6161101234567", headers=auth("cashier"))
    assert response.status_code == 404
    body = response.get_json()
    assert body["archived"] is True
    assert "archived" in body["error"]


def test_scan_lookup_requires_sign_in(client, product_factory):
    product_factory(barcode="6161101234567")
    assert client.get("/api/products/barcode/6161101234567").status_code == 401


def test_letters_and_symbols_barcodes_are_looked_up_exactly(client, cashier, auth, product_factory):
    product_factory(name="Loose rice", sku="R1", barcode="RICE-5KG")
    body = client.get("/api/products/barcode/RICE-5KG", headers=auth("cashier")).get_json()
    assert body["product"]["name"] == "Loose rice"


def test_repeated_scans_become_one_line_with_the_right_quantity(
    client, cashier, auth, product_factory
):
    coke = product_factory(name="Coke", sku="A", barcode="1111", price=80, stock=10)
    bread = product_factory(name="Bread", sku="B", barcode="2222", price=70, stock=10)
    # A, B, A as three separate lines (a client that did not merge) still sells A x2.
    body = client.post(
        "/api/sales",
        json={
            "items": [
                {"product_id": coke.id, "quantity": 1},
                {"product_id": bread.id, "quantity": 1},
                {"product_id": coke.id, "quantity": 1},
            ],
            "payment_method": "cash",
            "received_amount": "1000",
        },
        headers=auth("cashier"),
    ).get_json()
    quantities = {item["product_name"]: item["quantity"] for item in body["sale"]["items"]}
    assert quantities == {"Coke": 2, "Bread": 1}
    assert body["sale"]["subtotal"] == "230.00"
    db.session.expire_all()
    assert db.session.get(Product, coke.id).stock_quantity == 8


def test_scanned_out_of_stock_product_cannot_be_sold(client, cashier, auth, product_factory):
    product = product_factory(barcode="3333", stock=0)
    response = client.post(
        "/api/sales",
        json={
            "items": [{"product_id": product.id, "quantity": 1}],
            "payment_method": "cash",
            "received_amount": "1000",
        },
        headers=auth("cashier"),
    )
    assert response.status_code == 400
    assert "only has 0" in response.get_json()["error"]


def test_scanning_gives_cashier_no_management_rights(client, cashier, auth, product_factory):
    product = product_factory(barcode="4444")
    headers = auth("cashier")
    assert client.get("/api/products/barcode/4444", headers=headers).status_code == 200
    assert (
        client.patch("/api/products/%d" % product.id, json={"selling_price": "1"}, headers=headers).status_code
        == 403
    )
    assert client.post("/api/inventory/adjust", json={}, headers=headers).status_code == 403
