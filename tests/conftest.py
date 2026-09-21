import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Category, Product, ROLE_ADMIN, ROLE_CASHIER, User  # noqa: E402
from config import TestConfig  # noqa: E402


@pytest.fixture
def app():
    application = create_app(TestConfig)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _make_user(name, username, role, password="password123"):
    user = User(name=name, username=username, email="%s@example.com" % username, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def admin(app):
    return _make_user("Admin", "admin", ROLE_ADMIN)


@pytest.fixture
def cashier(app):
    return _make_user("Cashier", "cashier", ROLE_CASHIER)


@pytest.fixture
def auth(client):
    def _login(username, password="password123"):
        response = client.post(
            "/api/auth/login", json={"identifier": username, "password": password}
        )
        assert response.status_code == 200, response.get_json()
        token = response.get_json()["access_token"]
        return {"Authorization": "Bearer %s" % token}

    return _login


@pytest.fixture
def product_factory(app):
    def _create(name="Milk 500ml", sku="P001", barcode="6161234567890", cost=58, price=75, stock=10):
        category = Category.query.filter_by(name="Groceries").first()
        if category is None:
            category = Category(name="Groceries")
            db.session.add(category)
            db.session.flush()
        product = Product(
            name=name,
            sku=sku,
            barcode=barcode,
            category_id=category.id,
            cost_price=cost,
            selling_price=price,
            stock_quantity=stock,
            low_stock_threshold=5,
        )
        db.session.add(product)
        db.session.commit()
        return product

    return _create
