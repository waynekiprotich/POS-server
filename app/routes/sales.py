import csv
import io
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request

from ..extensions import db
from ..models import PAYMENT_METHODS, SALE_COMPLETED, SALE_VOIDED, Payment, Sale
from ..permissions import COSTS_VIEW, POS_SELL, SALES_VIEW_ALL, SALES_VOID
from ..services.sale_service import create_sale, receipt_payload, void_sale
from ..utils import dates
from ..utils.activity import log_activity
from ..utils.auth import auth_required, current_can, current_user, permission_required
from ..utils.errors import ApiError, Forbidden, NotFound
from ..utils.pagination import paginate
from ..utils.validation import arg_int, get_str, payload

bp = Blueprint("sales", __name__, url_prefix="/api/sales")

EXPORT_LIMIT = 50000


def _parse_day(value, field, end_of_day=False):
    try:
        day = datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ApiError("'%s' is not a valid date (use YYYY-MM-DD)." % value, field=field)
    return dates.day_end(day) if end_of_day else dates.day_start(day)


def _filtered_sales():
    """Sales visible to the current user, narrowed by the query string."""
    query = Sale.query
    if not current_can(SALES_VIEW_ALL):
        query = query.filter(Sale.cashier_id == current_user().id)
    else:
        cashier_id = arg_int("cashier_id")
        if cashier_id:
            query = query.filter(Sale.cashier_id == cashier_id)

    if request.args.get("start_date"):
        query = query.filter(
            Sale.created_at >= _parse_day(request.args["start_date"], "start_date")
        )
    if request.args.get("end_date"):
        query = query.filter(
            Sale.created_at
            <= _parse_day(request.args["end_date"], "end_date", end_of_day=True)
        )

    method = (request.args.get("payment_method") or "").lower()
    if method:
        if method not in PAYMENT_METHODS:
            raise ApiError("Unknown payment method.", field="payment_method")
        query = query.join(Payment, Payment.sale_id == Sale.id).filter(
            Payment.payment_method == method
        )

    status = request.args.get("status")
    if status in (SALE_COMPLETED, SALE_VOIDED):
        query = query.filter(Sale.status == status)

    term = (request.args.get("q") or "").strip().lstrip("#")
    if term:
        query = query.filter(Sale.sale_number.like("%%%s%%" % term))

    return query.order_by(Sale.created_at.desc(), Sale.id.desc())


@bp.get("")
@auth_required
def list_sales():
    page, meta = paginate(_filtered_sales())
    include_cost = current_can(COSTS_VIEW)
    return jsonify(
        {
            "items": [s.to_dict(include_cost=include_cost) for s in page.items],
            "pagination": meta,
        }
    )


@bp.get("/export")
@auth_required
def export_sales():
    """CSV of the filtered sales, generated locally (no internet needed)."""
    include_cost = current_can(COSTS_VIEW)
    tz = dates.business_tz()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    header = [
        "Receipt",
        "Date",
        "Time",
        "Cashier",
        "Status",
        "Payment",
        "Reference",
        "Items",
        "Subtotal",
        "Discount",
        "Tax",
        "Total",
    ]
    if include_cost:
        header.append("Gross profit")
    writer.writerow(header)
    for sale in _filtered_sales().limit(EXPORT_LIMIT):
        row = sale.to_dict(include_cost=include_cost)
        created = sale.created_at
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        local = created.astimezone(tz) if created else None
        line = [
            sale.sale_number,
            local.strftime("%Y-%m-%d") if local else "",
            local.strftime("%H:%M") if local else "",
            row["cashier_name"] or "",
            sale.status,
            row["payment_method"] or "",
            sale.payment.reference if sale.payment and sale.payment.reference else "",
            row["item_count"],
            row["subtotal"],
            row["discount"],
            row["tax"],
            row["total"],
        ]
        if include_cost:
            line.append(row["gross_profit"])
        writer.writerow([_safe_cell(value) for value in line])
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": 'attachment; filename="sales.csv"'},
    )


def _safe_cell(value):
    """Stop spreadsheet apps from running text that looks like a formula."""
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "@", "\t", "\r") or (text[:1] == "-" and not _is_number(text)):
        return "'" + text
    return text


def _is_number(text):
    try:
        float(text)
        return True
    except ValueError:
        return False


@bp.post("")
@permission_required(POS_SELL)
def post_sale():
    user = current_user()
    sale = create_sale(user, payload())
    log_activity(
        user,
        "sale.completed",
        "sale",
        sale.id,
        "Sale #%s for %s" % (sale.sale_number, sale.total),
    )
    db.session.commit()
    return jsonify(receipt_payload(sale, include_cost=current_can(COSTS_VIEW))), 201


@bp.get("/<int:sale_id>")
@auth_required
def get_sale(sale_id):
    user = current_user()
    sale = db.session.get(Sale, sale_id)
    if sale is None:
        raise NotFound("That sale could not be found.")
    if not current_can(SALES_VIEW_ALL) and sale.cashier_id != user.id:
        raise Forbidden("You can only view your own transactions.")
    return jsonify(receipt_payload(sale, include_cost=current_can(COSTS_VIEW)))


@bp.post("/<int:sale_id>/void")
@permission_required(SALES_VOID)
def post_void(sale_id):
    user = current_user()
    reason = get_str(payload(), "reason", required=True, max_length=255)
    sale = void_sale(sale_id, user, reason)
    log_activity(
        user,
        "sale.voided",
        "sale",
        sale.id,
        "Voided sale #%s (%s): %s" % (sale.sale_number, sale.total, reason),
    )
    db.session.commit()
    return jsonify(receipt_payload(sale, include_cost=current_can(COSTS_VIEW)))


@bp.get("/payment-methods")
@auth_required
def payment_methods():
    return jsonify({"items": list(PAYMENT_METHODS)})
