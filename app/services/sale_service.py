from decimal import Decimal
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import (
    MOVEMENT_SALE,
    MOVEMENT_VOID,
    PAYMENT_METHODS,
    SALE_COMPLETED,
    SALE_VOIDED,
    Business,
    Payment,
    Sale,
    SaleItem,
    Setting,
    utcnow,
)
from ..permissions import DISCOUNT_APPLY, has_permission
from ..utils.errors import ApiError, NotFound
from ..utils.money import quantize, to_decimal
from .inventory_service import apply_movement, lock_products

ZERO = Decimal("0")


def _tax_rate(settings):
    if settings.get("tax_enabled") != "true":
        return ZERO
    try:
        return Decimal(settings.get("tax_rate") or "0")
    except Exception:
        return ZERO


def create_sale(user, data):
    """Validate, price and persist a sale in one database transaction."""
    raw_items = data.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ApiError("Add at least one product before completing the sale.")

    wanted = {}
    for entry in raw_items:
        if not isinstance(entry, dict):
            raise ApiError("Each cart item must be an object.")
        try:
            product_id = int(entry.get("product_id"))
            quantity = int(entry.get("quantity"))
        except (TypeError, ValueError):
            raise ApiError("Each cart item needs a product and a quantity.")
        if quantity <= 0:
            raise ApiError("Quantity must be at least 1.")
        wanted[product_id] = wanted.get(product_id, 0) + quantity

    products = lock_products(wanted.keys())
    missing = [pid for pid in wanted if pid not in products]
    if missing:
        raise NotFound("One or more products in the cart no longer exist.")

    settings = Setting.as_dict()
    allow_negative = settings.get("allow_negative_stock") == "true"

    subtotal = ZERO
    line_items = []
    for product_id, quantity in wanted.items():
        product = products[product_id]
        if not product.is_active:
            raise ApiError("%s is no longer available for sale." % product.name)
        if not allow_negative and product.stock_quantity < quantity:
            raise ApiError(
                "Unable to complete sale because %s only has %d %s available."
                % (product.name, product.stock_quantity, product.unit)
            )
        unit_price = quantize(product.selling_price)
        line_total = quantize(unit_price * quantity)
        subtotal += line_total
        line_items.append((product, quantity, unit_price, line_total))

    subtotal = quantize(subtotal)

    discount = quantize(to_decimal(data.get("discount"), field="discount", default=ZERO))
    if discount < ZERO:
        raise ApiError("Discount cannot be negative.", field="discount")
    if discount > ZERO and not has_permission(user, DISCOUNT_APPLY):
        raise ApiError("Only a manager or the owner can apply a discount.", field="discount")
    if discount > subtotal:
        raise ApiError("Discount cannot be larger than the subtotal.", field="discount")

    taxable = subtotal - discount
    tax = quantize(taxable * _tax_rate(settings) / Decimal("100"))
    total = quantize(taxable + tax)

    method = (data.get("payment_method") or "").strip().lower()
    if method not in PAYMENT_METHODS:
        raise ApiError(
            "Select a payment method: %s." % ", ".join(PAYMENT_METHODS),
            field="payment_method",
        )

    reference = (data.get("reference") or "").strip() or None
    received = None
    change = None
    if method == "cash":
        received = quantize(
            to_decimal(data.get("received_amount"), field="received_amount")
        )
        if received < total:
            raise ApiError(
                "Cash received (%s) is less than the amount due (%s)."
                % (received, total),
                field="received_amount",
            )
        change = quantize(received - total)
    elif method == "mpesa" and not reference:
        raise ApiError(
            "Enter the M-Pesa transaction reference.", field="reference"
        )

    sale = Sale(
        business_id=Business.current_id(),
        sale_number="pending-%s" % uuid4().hex[:12],
        cashier_id=user.id,
        status=SALE_COMPLETED,
        subtotal=subtotal,
        discount=discount,
        tax=tax,
        total=total,
        payment_status="paid",
        note=(data.get("note") or "").strip() or None,
    )
    db.session.add(sale)
    db.session.flush()
    # The receipt number follows the primary key, so it stays unique under load.
    sale.sale_number = "%06d" % sale.id

    for product, quantity, unit_price, line_total in line_items:
        db.session.add(
            SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                product_name=product.name,
                product_sku=product.sku,
                quantity=quantity,
                unit_price=unit_price,
                cost_price=quantize(product.cost_price or ZERO),
                subtotal=line_total,
            )
        )
        apply_movement(
            product,
            -quantity,
            MOVEMENT_SALE,
            user=user,
            reference=sale.sale_number,
        )

    db.session.add(
        Payment(
            sale_id=sale.id,
            payment_method=method,
            amount=total,
            reference=reference,
            received_amount=received,
            change_amount=change,
        )
    )

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiError(
            "The sale could not be saved because of a conflict. Please try again."
        )
    return sale


def void_sale(sale_id, user, reason):
    """Mark a completed sale void and put its stock back, in one transaction.

    The sale, its items and payment stay exactly as recorded; reports simply
    stop counting it. Each returned item gets a VOID inventory movement.
    """
    # Take the write lock before reading the sale so two voids cannot race.
    sale = Sale.query.filter(Sale.id == sale_id).first()
    if sale is None:
        raise NotFound("That sale could not be found.")
    products = lock_products({item.product_id for item in sale.items if item.product_id})
    db.session.refresh(sale)
    if sale.status == SALE_VOIDED:
        raise ApiError("This sale has already been voided.")

    for item in sale.items:
        product = products.get(item.product_id)
        if product is None:
            continue
        apply_movement(
            product,
            item.quantity,
            MOVEMENT_VOID,
            user=user,
            reference=sale.sale_number,
            note=reason,
        )
    sale.status = SALE_VOIDED
    sale.voided_at = utcnow()
    sale.voided_by_id = user.id
    sale.void_reason = reason
    return sale


def receipt_payload(sale, settings=None, include_cost=False):
    settings = settings or Setting.as_dict()
    return {
        "sale": sale.to_dict(include_items=True, include_cost=include_cost),
        "business": {
            "name": settings.get("business_name"),
            "address": settings.get("business_address"),
            "phone": settings.get("business_phone"),
            "email": settings.get("business_email"),
            "tax_pin": settings.get("business_tax_pin"),
            "receipt_width": settings.get("receipt_width"),
            "show_cashier": settings.get("receipt_show_cashier") != "false",
            "footer": settings.get("receipt_footer"),
            "currency": settings.get("currency"),
            "currency_symbol": settings.get("currency_symbol"),
        },
    }
