from app.models import Business, Setting, User

SETUP = {
    "business_name": "Mama Mboga Store",
    "business_phone": "0700 000000",
    "currency": "kes",
    "currency_symbol": "KSh",
    "timezone": "Africa/Nairobi",
    "tax_enabled": True,
    "tax_rate": "16",
    "receipt_footer": "Karibu tena",
    "receipt_width": "58mm",
    "owner": {
        "name": "Wayne Owner",
        "username": "wayne",
        "email": "",
        "password": "owner-pass-1",
    },
}


def test_fresh_install_requires_setup(client):
    assert client.get("/api/setup/status").get_json()["setup_required"] is True


def test_setup_creates_business_owner_and_settings(client):
    response = client.post("/api/setup", json=SETUP)
    assert response.status_code == 201, response.get_json()

    business = Business.current()
    assert business.name == "Mama Mboga Store"
    assert business.setup_completed_at is not None

    owner = User.query.one()
    assert owner.role == "admin"
    assert owner.email is None
    assert owner.check_password("owner-pass-1")
    assert owner.business_id == business.id

    settings = Setting.as_dict()
    assert settings["currency"] == "KES"
    assert settings["tax_rate"] == "16"
    assert settings["receipt_width"] == "58mm"

    assert client.get("/api/setup/status").get_json()["setup_required"] is False
    login = client.post(
        "/api/auth/login", json={"identifier": "wayne", "password": "owner-pass-1"}
    )
    assert login.status_code == 200


def test_setup_cannot_run_twice(client):
    assert client.post("/api/setup", json=SETUP).status_code == 201
    second = dict(SETUP, owner=dict(SETUP["owner"], username="intruder"))
    response = client.post("/api/setup", json=second)
    assert response.status_code == 409
    assert User.query.count() == 1


def test_setup_validates_the_owner_account(client):
    bad = dict(SETUP, owner=dict(SETUP["owner"], password="short"))
    response = client.post("/api/setup", json=bad)
    assert response.status_code == 400
    assert response.get_json()["field"] == "password"
    assert Business.setup_completed() is False
    assert User.query.count() == 0


def test_setup_rejects_an_unknown_timezone(client):
    response = client.post("/api/setup", json=dict(SETUP, timezone="Moon/Base"))
    assert response.status_code == 400
    assert User.query.count() == 0
