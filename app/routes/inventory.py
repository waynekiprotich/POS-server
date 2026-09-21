from flask import Blueprint, jsonify, request

from ..extensions import db
from ..models import (
    MOVEMENT_ADJUSTMENT,
    MOVEMENT_RESTOCK,
    MOVEMENT_TYPES,
    InventoryMovement,
    Product,
)
from ..services.inventory_service import apply_movement, lock_products
from ..services.report_service import inventory_summary
from ..utils.activity import log_activity
from ..utils.auth import admin_required, current_user
from ..utils.errors import ApiError, NotFound
from ..utils.pagination import paginate
from ..utils.validation import arg_int, get_choice, get_int, get_str, payload

bp = Blueprint("inventory", __name__, url_prefix="/api/inventory")


@bp.get("")
@admin_required
def list_inventory():
    query = Product.query.filter(Product.is_active.is_(True))

    term = (request.args.get("q") or "").strip().lower()
    if term:
        like = "%%%s%%" % term
        query = query.filter(
            db.or_(
                db.func.lower(Product.name).like(like),
                db.func.lower(Product.sku).like(like),
            )
        )

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

    query = query.order_by(Product.stock_quantity.asc(), Product.name.asc())
    page, meta = paginate(query)
    return jsonify(
        {
            "items": [p.to_dict() for p in page.items],
            "pagination": meta,
            "summary": inventory_summary(),
        }
    )


@bp.post("/adjust")
@admin_required
def adjust_inventory():
    user = current_user()
    data = payload()
    product_id = get_int(data, "product_id", required=True)
    # Row lock so a sale on another till cannot interleave with this change.
    product = lock_products([product_id]).get(product_id)
    if product is None:
        raise NotFound("That product could not be found.")

    movement_type = get_choice(
        data, "movement_type", MOVEMENT_TYPES, default=MOVEMENT_ADJUSTMENT
    )
    note = get_str(data, "note", max_length=255)

    if "new_quantity" in data and data.get("new_quantity") not in (None, ""):
        new_quantity = get_int(data, "new_quantity", minimum=0)
        change = new_quantity - (product.stock_quantity or 0)
    else:
        change = get_int(data, "quantity_change", required=True)

    if change == 0:
        raise ApiError("Enter a quantity that changes the current stock level.")
    if change > 0 and movement_type not in (MOVEMENT_RESTOCK, MOVEMENT_ADJUSTMENT, "RETURN"):
        movement_type = MOVEMENT_RESTOCK

    previous = product.stock_quantity
    apply_movement(product, change, movement_type, user=user, note=note)
    log_activity(
        user,
        "inventory.adjusted",
        "product",
        product.id,
        "%s stock %d to %d (%s)"
        % (product.name, previous, product.stock_quantity, movement_type),
    )
    db.session.commit()
    return jsonify({"product": product.to_dict()})


@bp.get("/movements")
@admin_required
def list_movements():
    query = InventoryMovement.query
    product_id = request.args.get("product_id")
    if product_id:
        query = query.filter(InventoryMovement.product_id == arg_int("product_id"))
    movement_type = request.args.get("movement_type")
    if movement_type:
        query = query.filter(InventoryMovement.movement_type == movement_type.upper())
    query = query.order_by(InventoryMovement.created_at.desc(), InventoryMovement.id.desc())
    page, meta = paginate(query)
    return jsonify({"items": [m.to_dict() for m in page.items], "pagination": meta})
