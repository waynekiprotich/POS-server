def test_cashier_cannot_create_product(client, cashier, auth):
    headers = auth("cashier")
    response = client.post("/api/products", json={"name": "X", "selling_price": 10}, headers=headers)
    assert response.status_code == 403


def test_admin_creates_product_with_generated_sku(client, admin, auth):
    headers = auth("admin")
    response = client.post(
        "/api/products",
        json={"name": "Bread", "cost_price": "52", "selling_price": "70", "stock_quantity": 12},
        headers=headers,
    )
    body = response.get_json()
    assert response.status_code == 201, body
    assert body["product"]["sku"].startswith("PROD-")
    assert body["product"]["stock_quantity"] == 12


def test_duplicate_barcode_is_rejected(client, admin, auth, product_factory):
    product_factory()
    headers = auth("admin")
    response = client.post(
        "/api/products",
        json={"name": "Other", "barcode": "6161234567890", "selling_price": "10"},
        headers=headers,
    )
    assert response.status_code == 409
    assert "already assigned" in response.get_json()["error"]


def test_barcode_lookup_hit_and_miss(client, cashier, auth, product_factory):
    product_factory()
    headers = auth("cashier")
    hit = client.get("/api/products/barcode/6161234567890", headers=headers)
    assert hit.status_code == 200
    assert hit.get_json()["product"]["name"] == "Milk 500ml"

    miss = client.get("/api/products/barcode/0000000000000", headers=headers)
    assert miss.status_code == 404
    assert miss.get_json()["found"] is False


def test_cashier_does_not_see_cost_price(client, cashier, auth, product_factory):
    product_factory()
    body = client.get("/api/products", headers=auth("cashier")).get_json()
    assert "cost_price" not in body["items"][0]


def test_stock_cannot_be_edited_from_product_form(client, admin, auth, product_factory):
    product = product_factory()
    response = client.patch(
        "/api/products/%d" % product.id, json={"stock_quantity": 99}, headers=auth("admin")
    )
    assert response.status_code == 400
    assert "inventory adjustment" in response.get_json()["error"]
