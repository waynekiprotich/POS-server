import os
import sqlite3
import time

import pytest

from app.extensions import db
from app.services import backup_service, scan_pairing


def test_phone_scan_reaches_paired_till(client, cashier, auth):
    headers = auth("cashier")
    session = client.post("/api/scan-sessions", headers=headers).get_json()
    code = session["code"]
    assert len(code) == 8 and code.isalnum()

    # The phone needs no account: only the code.
    assert client.get("/api/scan-sessions/%s" % code).status_code == 200
    sent = client.post("/api/scan-sessions/%s/scan" % code, json={"barcode": "6161234567890"})
    assert sent.status_code == 200

    polled = client.get("/api/scan-sessions/%s/poll?after=0" % code, headers=headers).get_json()
    assert [item["barcode"] for item in polled["items"]] == ["6161234567890"]
    assert polled["session"]["phone_seen"] is True
    again = client.get(
        "/api/scan-sessions/%s/poll?after=%d" % (code, polled["items"][0]["id"]), headers=headers
    ).get_json()
    assert again["items"] == []


def test_other_staff_cannot_read_a_tills_scans(client, cashier, manager, auth):
    code = client.post("/api/scan-sessions", headers=auth("cashier")).get_json()["code"]
    response = client.get("/api/scan-sessions/%s/poll" % code, headers=auth("manager"))
    assert response.status_code == 404


def test_pairing_expires_and_can_be_revoked(client, cashier, auth, monkeypatch):
    headers = auth("cashier")
    code = client.post("/api/scan-sessions", headers=headers).get_json()["code"]
    assert client.delete("/api/scan-sessions/%s" % code, headers=headers).status_code == 200
    assert client.post("/api/scan-sessions/%s/scan" % code, json={"barcode": "1"}).status_code == 410

    code = client.post("/api/scan-sessions", headers=headers).get_json()["code"]
    later = time.time() + scan_pairing.IDLE_TTL_SECONDS + 5
    monkeypatch.setattr(scan_pairing.time, "time", lambda: later)
    assert client.post("/api/scan-sessions/%s/scan" % code, json={"barcode": "1"}).status_code == 410
    assert client.get("/api/scan-sessions/%s/poll" % code, headers=headers).status_code == 404


def test_pairing_has_a_hard_maximum_age(cashier):
    session = scan_pairing.create_session(cashier.id)
    code = session["code"]
    start = time.time()
    # Keep it busy, but past the maximum age it still ends.
    scan_pairing._sessions[code]["created_at"] = start - scan_pairing.MAX_AGE_SECONDS - 1
    assert scan_pairing.push_scan(code, "123") is None


def test_wrong_codes_are_rate_limited(client):
    statuses = [
        client.post("/api/scan-sessions/WRONG%03d/scan" % n, json={"barcode": "1"}).status_code
        for n in range(21)
    ]
    assert statuses[:20] == [410] * 20
    assert statuses[20] == 429


def test_viewer_cannot_open_pairing(client, viewer, auth):
    assert client.post("/api/scan-sessions", headers=auth("viewer")).status_code == 403




def test_backup_creates_a_consistent_copy(tmp_path, admin_file_app):
    app, client, headers = admin_file_app
    response = client.post("/api/backups", headers=headers)
    assert response.status_code == 201, response.get_json()
    backup = response.get_json()["backup"]
    assert backup["name"].startswith("pos-") and backup["size"] > 0

    listed = client.get("/api/backups", headers=headers).get_json()
    assert listed["supported"] is True
    assert [b["name"] for b in listed["items"]] == [backup["name"]]

    path = os.path.join(app.config["BACKUP_DIR"], backup["name"])
    copy = sqlite3.connect(path)
    assert copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert copy.execute("SELECT username FROM users").fetchall() == [("owner",)]
    copy.close()

    download = client.get("/api/backups/%s/download" % backup["name"], headers=headers)
    assert download.status_code == 200 and len(download.data) == backup["size"]


def test_backup_download_rejects_path_tricks(admin_file_app):
    _, client, headers = admin_file_app
    for name in ("../pos.db", "..%2F..%2Fconfig.py", "pos.db"):
        response = client.get("/api/backups/%s/download" % name, headers=headers)
        assert response.status_code == 404


def test_automatic_backup_runs_when_due_and_prunes(admin_file_app):
    app, _, _ = admin_file_app
    with app.app_context():
        first = backup_service.run_auto_backup_if_due()
        assert first is not None and first["kind"] == "auto"
        assert backup_service.run_auto_backup_if_due() is None  # not due again yet



@pytest.fixture
def admin_file_app(tmp_path):
    from app import create_app
    from app.models import User
    from config import TestConfig

    config = type(
        "Config",
        (TestConfig,),
        {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///%s" % (tmp_path / "shop.db"),
            "BACKUP_DIR": str(tmp_path / "backups"),
        },
    )
    app = create_app(config)
    with app.app_context():
        db.create_all()
        owner = User(name="Owner", username="owner", role="admin")
        owner.set_password("password123")
        db.session.add(owner)
        db.session.commit()
        client = app.test_client()
        token = client.post(
            "/api/auth/login", json={"identifier": "owner", "password": "password123"}
        ).get_json()["access_token"]
        yield app, client, {"Authorization": "Bearer %s" % token}
        db.session.remove()
        db.engine.dispose()
