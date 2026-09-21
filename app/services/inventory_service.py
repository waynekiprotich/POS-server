from ..extensions import db
from ..models import InventoryMovement, Product, Setting
from ..utils.errors import ApiError


def negative_stock_allowed():
    return Setting.get("allow_negative_stock", "false") == "true"


def apply_movement(
    product,
    quantity_change,
    movement_type,
    user=None,
    reference=None,
    note=None,
):
    """Change stock and record the movement. Caller owns the transaction."""
    previous = product.stock_quantity or 0
    new_quantity = previous + quantity_change
    if new_quantity < 0 and not negative_stock_allowed():
        raise ApiError(
            "Unable to update %s because only %d %s remain in stock."
            % (product.name, previous, product.unit)
        )
    product.stock_quantity = new_quantity
    db.session.add(
        InventoryMovement(
            product_id=product.id,
            user_id=user.id if user else None,
            movement_type=movement_type,
            quantity_change=quantity_change,
            previous_quantity=previous,
            new_quantity=new_quantity,
            reference=reference,
            note=note,
        )
    )
    return product


def lock_products(product_ids):
    """Load products for update so two tills cannot oversell the same stock."""
    if not product_ids:
        return {}
    query = Product.query.filter(Product.id.in_(list(product_ids)))
    if db.engine.dialect.name != "sqlite":
        query = query.with_for_update()
    return {p.id: p for p in query.all()}
