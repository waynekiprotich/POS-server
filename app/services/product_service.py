from sqlalchemy import func

from ..extensions import db
from ..models import Product
from ..utils.errors import Conflict

SKU_PREFIX = "PROD-"


def generate_sku():
    """Next sequential SKU, e.g. PROD-000001."""
    last = (
        db.session.query(func.max(Product.id)).scalar() or 0
    )
    candidate_number = last + 1
    while True:
        sku = "%s%06d" % (SKU_PREFIX, candidate_number)
        exists = Product.query.filter(func.lower(Product.sku) == sku.lower()).first()
        if not exists:
            return sku
        candidate_number += 1


def assert_sku_available(sku, product_id=None):
    query = Product.query.filter(func.lower(Product.sku) == sku.lower())
    if product_id:
        query = query.filter(Product.id != product_id)
    if query.first():
        raise Conflict("SKU '%s' is already used by another product." % sku, field="sku")


def assert_barcode_available(barcode, product_id=None):
    if not barcode:
        return
    query = Product.query.filter(Product.barcode == barcode)
    if product_id:
        query = query.filter(Product.id != product_id)
    existing = query.first()
    if existing:
        raise Conflict(
            "Barcode %s is already assigned to %s." % (barcode, existing.name),
            field="barcode",
        )
