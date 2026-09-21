def test_login_returns_token_and_user(client, admin):
    response = client.post(
        "/api/auth/login", json={"identifier": "admin", "password": "password123"}
    )
    body = response.get_json()
    assert response.status_code == 200
    assert body["user"]["role"] == "admin"
    assert body["access_token"]


def test_login_rejects_bad_password(client, admin):
    response = client.post(
        "/api/auth/login", json={"identifier": "admin", "password": "wrong"}
    )
    assert response.status_code == 401
    assert response.get_json()["error"] == "Incorrect username or password."


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_password_is_hashed(admin):
    assert admin.password_hash != "password123"
    assert admin.check_password("password123")
