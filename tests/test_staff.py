from app.models import ActivityLog, User


def test_cashier_logs_in_with_pin(client, cashier):
    users = client.get("/api/auth/pin-users").get_json()
    assert [u["name"] for u in users["items"]] == ["Cashier"]
    assert "username" not in users["items"][0]

    response = client.post("/api/auth/pin-login", json={"user_id": cashier.id, "pin": "4321"})
    body = response.get_json()
    assert response.status_code == 200, body
    assert body["user"]["role"] == "cashier"
    assert "pos.sell" in body["user"]["permissions"]
    from app.extensions import db

    assert db.session.get(User, cashier.id).last_login_at is not None


def test_wrong_pin_is_rejected_and_rate_limited(app, client, cashier):
    app.config["PIN_ATTEMPT_LIMIT"] = 3
    for _ in range(3):
        response = client.post(
            "/api/auth/pin-login", json={"user_id": cashier.id, "pin": "0000"}
        )
        assert response.status_code == 401
    locked = client.post("/api/auth/pin-login", json={"user_id": cashier.id, "pin": "4321"})
    assert locked.status_code == 429


def test_pin_is_hashed_never_stored_raw(cashier):
    assert cashier.pin_hash and "4321" not in cashier.pin_hash
    assert cashier.check_pin("4321") and not cashier.check_pin("1234")


def test_owner_cannot_use_pin_login(client, admin):
    admin.set_pin("1111")
    from app.extensions import db

    db.session.commit()
    response = client.post("/api/auth/pin-login", json={"user_id": admin.id, "pin": "1111"})
    assert response.status_code == 401
    ids = [u["id"] for u in client.get("/api/auth/pin-users").get_json()["items"]]
    assert admin.id not in ids


def test_disabled_user_cannot_sign_in_or_use_old_token(client, admin, cashier, auth):
    cashier_headers = auth("cashier")
    admin_headers = auth("admin")
    response = client.patch(
        "/api/users/%d" % cashier.id, json={"is_active": False}, headers=admin_headers
    )
    assert response.status_code == 200

    assert client.get("/api/auth/me", headers=cashier_headers).status_code == 401
    assert (
        client.post("/api/auth/pin-login", json={"user_id": cashier.id, "pin": "4321"}).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login", json={"identifier": "cashier", "password": "password123"}
        ).status_code
        == 401
    )


def test_owner_creates_cashier_with_pin(client, admin, auth):
    response = client.post(
        "/api/users",
        json={
            "name": "Mary",
            "username": "mary",
            "password": "mary-pass-1",
            "role": "cashier",
            "pin": "2468",
        },
        headers=auth("admin"),
    )
    body = response.get_json()
    assert response.status_code == 201, body
    assert body["user"]["has_pin"] is True
    assert body["user"]["email"] is None
    login = client.post("/api/auth/pin-login", json={"user_id": body["user"]["id"], "pin": "2468"})
    assert login.status_code == 200
    logged = ActivityLog.query.filter_by(action="user.created").one()
    assert "2468" not in (logged.description or "")
    assert "mary-pass-1" not in (logged.description or "")


def test_manager_can_manage_cashiers_but_not_owners(client, admin, manager, cashier, auth):
    headers = auth("manager")
    assert (
        client.patch("/api/users/%d" % cashier.id, json={"pin": "9999"}, headers=headers).status_code
        == 200
    )
    assert (
        client.patch(
            "/api/users/%d" % admin.id, json={"is_active": False}, headers=headers
        ).status_code
        == 403
    )
    promote = client.patch("/api/users/%d" % cashier.id, json={"role": "admin"}, headers=headers)
    assert promote.status_code == 403
    create_owner = client.post(
        "/api/users",
        json={"name": "X", "username": "x", "password": "password123", "role": "admin"},
        headers=headers,
    )
    assert create_owner.status_code == 403


def test_cashier_cannot_manage_staff(client, cashier, auth):
    headers = auth("cashier")
    assert client.get("/api/users", headers=headers).status_code == 403
    assert (
        client.post(
            "/api/users",
            json={"name": "X", "username": "x", "password": "password123"},
            headers=headers,
        ).status_code
        == 403
    )


def test_owner_cannot_demote_or_disable_themselves(client, admin, auth):
    headers = auth("admin")
    demote = client.patch("/api/users/%d" % admin.id, json={"role": "manager"}, headers=headers)
    assert demote.status_code == 400 and demote.get_json()["field"] == "role"
    disable = client.patch("/api/users/%d" % admin.id, json={"is_active": False}, headers=headers)
    assert disable.status_code == 400 and disable.get_json()["field"] == "is_active"


def test_staff_list_shows_sales_today_and_last_login(client, admin, cashier, auth, product_factory):
    product = product_factory(stock=5, price=100)
    client.post(
        "/api/sales",
        json={
            "items": [{"product_id": product.id, "quantity": 1}],
            "payment_method": "cash",
            "received_amount": "100",
        },
        headers=auth("cashier"),
    )
    items = client.get("/api/users", headers=auth("admin")).get_json()["items"]
    row = next(u for u in items if u["username"] == "cashier")
    assert row["sales_today"] == {"count": 1, "total": "100.00"}
    assert row["last_login_at"]


def test_cashier_sets_own_pin_with_password(client, cashier, auth):
    headers = auth("cashier")
    bad = client.post(
        "/api/auth/change-pin", json={"current_password": "nope", "pin": "1357"}, headers=headers
    )
    assert bad.status_code == 400
    ok = client.post(
        "/api/auth/change-pin",
        json={"current_password": "password123", "pin": "1357"},
        headers=headers,
    )
    assert ok.status_code == 200
    login = client.post("/api/auth/pin-login", json={"user_id": cashier.id, "pin": "1357"})
    assert login.status_code == 200
