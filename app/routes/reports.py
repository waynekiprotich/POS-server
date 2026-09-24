from flask import Blueprint, jsonify, request

from ..models import Sale
from ..permissions import COSTS_VIEW, REPORTS_VIEW
from ..services.report_service import (
    cashier_performance,
    category_performance,
    inventory_summary,
    low_stock_products,
    payment_breakdown,
    product_performance,
    resolve_range,
    sales_summary,
    sales_trend,
)
from ..utils.auth import current_can, permission_required
from ..utils.errors import ApiError

bp = Blueprint("reports", __name__, url_prefix="/api/reports")


def _range():
    start, end, start_date, end_date = resolve_range(request.args)
    meta = {
        "period": request.args.get("period", "today"),
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
    }
    return start, end, meta


@bp.get("/summary")
@permission_required(REPORTS_VIEW)
def summary():
    start, end, meta = _range()
    try:
        trend_days = int(request.args.get("trend_days", 7))
    except (TypeError, ValueError):
        raise ApiError("trend_days must be a whole number.", field="trend_days")
    trend_days = max(1, min(trend_days, 90))

    recent = (
        Sale.query.order_by(Sale.created_at.desc(), Sale.id.desc()).limit(8).all()
    )
    return jsonify(
        {
            "range": meta,
            "totals": sales_summary(start, end),
            "trend": sales_trend(trend_days),
            "recent_sales": [s.to_dict(include_cost=current_can(COSTS_VIEW)) for s in recent],
            "low_stock": [p.to_dict() for p in low_stock_products(8)],
            "top_products": product_performance(start, end, limit=5, order_by="units"),
            "payments": payment_breakdown(start, end),
            "inventory": inventory_summary(),
        }
    )


@bp.get("/sales")
@permission_required(REPORTS_VIEW)
def sales_report():
    start, end, meta = _range()
    return jsonify(
        {
            "range": meta,
            "totals": sales_summary(start, end),
            "payments": payment_breakdown(start, end),
        }
    )


@bp.get("/products")
@permission_required(REPORTS_VIEW)
def products_report():
    start, end, meta = _range()
    order_by = request.args.get("order_by", "units")
    return jsonify(
        {
            "range": meta,
            "items": product_performance(start, end, limit=100, order_by=order_by),
        }
    )


@bp.get("/profit")
@permission_required(REPORTS_VIEW)
def profit_report():
    start, end, meta = _range()
    return jsonify(
        {
            "range": meta,
            "totals": sales_summary(start, end),
            "items": product_performance(start, end, limit=100, order_by="profit"),
        }
    )


@bp.get("/payments")
@permission_required(REPORTS_VIEW)
def payments_report():
    start, end, meta = _range()
    return jsonify({"range": meta, "items": payment_breakdown(start, end)})


@bp.get("/inventory")
@permission_required(REPORTS_VIEW)
def inventory_report():
    return jsonify(
        {
            "summary": inventory_summary(),
            "low_stock": [p.to_dict() for p in low_stock_products(100)],
        }
    )


@bp.get("/categories")
@permission_required(REPORTS_VIEW)
def categories_report():
    start, end, meta = _range()
    return jsonify({"range": meta, "items": category_performance(start, end)})


@bp.get("/cashiers")
@permission_required(REPORTS_VIEW)
def cashiers_report():
    start, end, meta = _range()
    return jsonify({"range": meta, "items": cashier_performance(start, end)})
