from flask import Blueprint, jsonify, request
from sqlalchemy import or_

from ..extensions import db
from ..models import (
    MOVEMENT_RESTOCK,
    Business,
    Category,
    Product,
    Setting,
)
from ..permissions import COSTS_VIEW, PRODUCTS_MANAGE
from ..services.inventory_service import apply_movement
from ..services.product_service import (
    assert_barcode_available,
    assert_sku_available,
    generate_sku,
)
from ..utils.activity import log_activity
from ..utils.auth import auth_required, current_can, current_user, permission_required
from ..utils.errors import ApiError, NotFound
from ..utils.money import money_str, quantize, to_decimal
from ..utils.pagination import paginate
from ..utils.validation import arg_int, get_bool, get_int, get_str, payload

bp = Blueprint("products", __name__, url_prefix="/api/products")


def _get_or_404(product_id):
    product = db.session.get(Product, product_id)
    if product is None:
        raise NotFound("That product could not be found.")
    return product


def _search_filter(query, term):
    like = "%%%s%%" % term.lower()
    return query.filter(
        or_(
            db.func.lower(Product.name).like(like),
            db.func.lower(Product.sku).like(like),
            db.func.lower(db.func.coalesce(Product.barcode, "")).like(like),
        )
    )


@bp.get("")
@auth_required
def list_products():
    query = Product.query

    term = (request.args.get("q") or "").strip()
    if term:
        query = _search_filter(query, term)

    category_id = request.args.get("category_id")
    if category_id:
        query = query.filter(Product.category_id == arg_int("category_id"))

    status = (request.args.get("status") or "").strip()
    if status == "active":
        query = query.filter(Product.is_active.is_(True))
    elif status == "archived":
        query = query.filter(Product.is_active.is_(False))
    else:
        query = query.filter(Product.is_active.is_(True))

    stock = (request.args.get("stock") or "").strip()
    if stock == "low":
        query = query.filter(
            Product.stock_quantity > 0,
            Product.stock_quantity <= Product.low_stock_threshold,
        )
    elif stock == "out":
        query = query.filter(Product.stock_quantity <= 0)
    elif stock == "in":
        query = query.filter(Product.stock_quantity > Product.low_stock_threshold)

    query = query.order_by(Product.name.asc())
    page, meta = paginate(query)
    return jsonify(
        {
            "items": [p.to_dict(include_cost=current_can(COSTS_VIEW)) for p in page.items],
            "pagination": meta,
        }
    )


@bp.get("/barcode/<barcode>")
@auth_required
def lookup_barcode(barcode):
    product = Product.query.filter(
        Product.barcode == barcode.strip(), Product.is_active.is_(True)
    ).first()
    if product is None:
        archived = Product.query.filter(Product.barcode == barcode.strip()).first()
        if archived is not None:
            return (
                jsonify(
                    {
                        "found": False,
                        "archived": True,
                        "barcode": barcode.strip(),
                        "error": "%s is archived and cannot be sold." % archived.name,
                    }
                ),
                404,
            )
        return jsonify({"found": False, "barcode": barcode.strip()}), 404
    return jsonify({"found": True, "product": product.to_dict(include_cost=current_can(COSTS_VIEW))})


@bp.get("/<int:product_id>")
@auth_required
def get_product(product_id):
    product = _get_or_404(product_id)
    return jsonify({"product": product.to_dict(include_cost=current_can(COSTS_VIEW))})


def _apply_fields(product, data, creating):
    name = get_str(data, "name", required=creating, max_length=180)
    if name is not None:
        product.name = name

    description = get_str(data, "description", max_length=2000)
    if "description" in data:
        product.description = description

    if "category_id" in data:
        category_id = data.get("category_id")
        if category_id in (None, "", 0):
            product.category_id = None
        else:
            category_id = get_int(data, "category_id")
            if db.session.get(Category, category_id) is None:
                raise NotFound("That category could not be found.")
            product.category_id = category_id

    for field in ("cost_price", "selling_price"):
        if field in data or creating:
            value = quantize(to_decimal(data.get(field), field=field, default=quantize(0)))
            if value < 0:
                raise ApiError("%s cannot be negative." % field.replace("_", " "), field=field)
            setattr(product, field, value)

    if "low_stock_threshold" in data or creating:
        default_threshold = int(Setting.get("default_low_stock_threshold", "5") or 5)
        product.low_stock_threshold = get_int(
            data, "low_stock_threshold", default=default_threshold, minimum=0
        )

    unit = get_str(data, "unit", max_length=20)
    if unit:
        product.unit = unit
    elif creating and not product.unit:
        product.unit = "pc"

    for field in ("brand", "supplier", "image_url"):
        if field in data:
            setattr(product, field, get_str(data, field, max_length=500))

    if "is_active" in data:
        product.is_active = bool(get_bool(data, "is_active", default=True))


@bp.post("")
@permission_required(PRODUCTS_MANAGE)
def create_product():
    user = current_user()
    data = payload()
    product = Product(business_id=Business.current_id())
    _apply_fields(product, data, creating=True)

    sku = get_str(data, "sku", max_length=60) or generate_sku()
    assert_sku_available(sku)
    product.sku = sku

    barcode = get_str(data, "barcode", max_length=64)
    assert_barcode_available(barcode)
    product.barcode = barcode

    opening_stock = get_int(data, "stock_quantity", default=0, minimum=0)
    product.stock_quantity = 0

    db.session.add(product)
    db.session.flush()

    if opening_stock:
        apply_movement(
            product,
            opening_stock,
            MOVEMENT_RESTOCK,
            user=user,
            note="Opening stock",
        )

    log_activity(
        user,
        "product.created",
        "product",
        product.id,
        "Created product %s (%s)" % (product.name, product.sku),
    )
    db.session.commit()
    return jsonify({"product": product.to_dict()}), 201


@bp.patch("/<int:product_id>")
@permission_required(PRODUCTS_MANAGE)
def update_product(product_id):
    user = current_user()
    product = _get_or_404(product_id)
    data = payload()
    old_price = product.selling_price

    _apply_fields(product, data, creating=False)

    if "sku" in data:
        sku = get_str(data, "sku", required=True, max_length=60)
        assert_sku_available(sku, product.id)
        product.sku = sku

    if "barcode" in data:
        barcode = get_str(data, "barcode", max_length=64)
        assert_barcode_available(barcode, product.id)
        product.barcode = barcode

    if "stock_quantity" in data:
        raise ApiError(
            "Stock is changed through an inventory adjustment so the change is recorded.",
            field="stock_quantity",
        )

    if old_price != product.selling_price:
        log_activity(
            user,
            "product.price_changed",
            "product",
            product.id,
            "%s price changed from %s to %s"
            % (product.name, money_str(old_price), money_str(product.selling_price)),
        )
    log_activity(
        user, "product.updated", "product", product.id, "Updated product %s" % product.name
    )
    db.session.commit()
    return jsonify({"product": product.to_dict()})


@bp.delete("/<int:product_id>")
@permission_required(PRODUCTS_MANAGE)
def archive_product(product_id):
    user = current_user()
    product = _get_or_404(product_id)
    product.is_active = False
    log_activity(
        user, "product.archived", "product", product.id, "Archived %s" % product.name
    )
    db.session.commit()
    return jsonify({"product": product.to_dict()})


@bp.post("/<int:product_id>/restore")
@permission_required(PRODUCTS_MANAGE)
def restore_product(product_id):
    user = current_user()
    product = _get_or_404(product_id)
    product.is_active = True
    log_activity(
        user, "product.restored", "product", product.id, "Restored %s" % product.name
    )
    db.session.commit()
    return jsonify({"product": product.to_dict()})
