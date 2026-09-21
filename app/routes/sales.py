from datetime import datetime

from flask import Blueprint, jsonify, request

from ..extensions import db
from ..models import PAYMENT_METHODS, Payment, Sale
from ..services.sale_service import create_sale, receipt_payload
from ..utils import dates
from ..utils.activity import log_activity
from ..utils.auth import auth_required, current_user
from ..utils.errors import ApiError, Forbidden, NotFound
from ..utils.pagination import paginate
from ..utils.validation import arg_int, payload

bp = Blueprint("sales", __name__, url_prefix="/api/sales")


def _parse_day(value, field, end_of_day=False):
    try:
        day = datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ApiError("'%s' is not a valid date (use YYYY-MM-DD)." % value, field=field)
    return dates.day_end(day) if end_of_day else dates.day_start(day)


@bp.get("")
@auth_required
def list_sales():
    user = current_user()
    query = Sale.query

    if not user.is_admin:
        query = query.filter(Sale.cashier_id == user.id)
    elif request.args.get("cashier_id"):
        query = query.filter(Sale.cashier_id == arg_int("cashier_id"))

    if request.args.get("start_date"):
        query = query.filter(
            Sale.created_at >= _parse_day(request.args["start_date"], "start_date")
        )
    if request.args.get("end_date"):
        query = query.filter(
            Sale.created_at
            <= _parse_day(request.args["end_date"], "end_date", end_of_day=True)
        )

    method = request.args.get("payment_method")
    if method:
        query = query.join(Payment, Payment.sale_id == Sale.id).filter(
            Payment.payment_method == method.lower()
        )

    term = (request.args.get("q") or "").strip()
    if term:
        query = query.filter(Sale.sale_number.like("%%%s%%" % term))

    query = query.order_by(Sale.created_at.desc(), Sale.id.desc())
    page, meta = paginate(query)
    return jsonify(
        {
            "items": [s.to_dict(include_cost=user.is_admin) for s in page.items],
            "pagination": meta,
        }
    )


@bp.post("")
@auth_required
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
    return jsonify(receipt_payload(sale)), 201


@bp.get("/<int:sale_id>")
@auth_required
def get_sale(sale_id):
    user = current_user()
    sale = db.session.get(Sale, sale_id)
    if sale is None:
        raise NotFound("That sale could not be found.")
    if not user.is_admin and sale.cashier_id != user.id:
        raise Forbidden("You can only view your own transactions.")
    return jsonify(receipt_payload(sale))


@bp.get("/payment-methods")
@auth_required
def payment_methods():
    return jsonify({"items": list(PAYMENT_METHODS)})
