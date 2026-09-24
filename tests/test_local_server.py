import pytest

from app import create_app
from app.utils import network
from config import TestConfig


@pytest.fixture
def served(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>POS app</html>")
    (dist / "assets" / "app-abc123.js").write_text("console.log(1)")
    config = type("Config", (TestConfig,), {"FRONTEND_DIST": str(dist)})
    return create_app(config).test_client()


def test_flask_serves_the_built_app_and_client_routes(served):
    home = served.get("/")
    assert home.status_code == 200 and b"POS app" in home.data
    # Deep links such as the phone scanner page load the app shell.
    scan = served.get("/scan/ABCD2345")
    assert scan.status_code == 200 and b"POS app" in scan.data
    asset = served.get("/assets/app-abc123.js")
    assert asset.status_code == 200
    assert "immutable" in asset.headers["Cache-Control"]


def test_unknown_api_paths_stay_json_404(served):
    response = served.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.is_json


def test_static_serving_blocks_path_traversal(served):
    response = served.get("/../config.py")
    assert b"SECRET" not in response.data


def test_security_headers(served):
    response = served.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "camera=(self)" in response.headers["Permissions-Policy"]


def test_missing_build_explains_what_to_do(tmp_path):
    config = type("Config", (TestConfig,), {"FRONTEND_DIST": str(tmp_path / "nothing")})
    response = create_app(config).test_client().get("/pos")
    assert response.status_code == 404
    assert "setup.sh" in response.get_json()["error"]


def test_network_info_lists_lan_addresses(client, cashier, auth, monkeypatch):
    monkeypatch.setattr(network, "lan_ipv4_addresses", lambda: ["192.168.1.20"])
    from app.routes import system

    monkeypatch.setattr(system, "lan_ipv4_addresses", lambda: ["192.168.1.20"])
    body = client.get("/api/system/network", headers=auth("cashier")).get_json()
    assert body["lan_addresses"] == ["192.168.1.20"]
    assert body["lan_urls"] == ["http://192.168.1.20"]


def test_lan_detection_only_returns_private_addresses():
    for address in network.lan_ipv4_addresses():
        assert network._is_lan(address)
    assert not network._is_lan("8.8.8.8")
    assert not network._is_lan("127.0.0.1")
    assert network._is_lan("192.168.1.20")
