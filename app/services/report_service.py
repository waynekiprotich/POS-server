from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import case, func

from ..extensions import db
from ..models import SALE_COMPLETED, Category, Payment, Product, Sale, SaleItem, User
from ..utils import dates
from ..utils.errors import ApiError
from ..utils.money import money_str, quantize

ZERO = Decimal("0")


def _parse_date(value, field):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ApiError("'%s' is not a valid date (use YYYY-MM-DD)." % value, field=field)


def resolve_range(args):
    """Turn report filters (local calendar days) into an inclusive UTC window."""
    period = (args.get("period") or "today").lower()
    today = dates.today()

    if period == "custom":
        start_date = _parse_date(args.get("start_date"), "start_date")
        end_date = _parse_date(args.get("end_date"), "end_date")
    elif period == "today":
        start_date = end_date = today
    elif period == "yesterday":
        start_date = end_date = today - timedelta(days=1)
    elif period == "week":
        start_date = today - timedelta(days=today.weekday())
        end_date = today
    elif period == "month":
        start_date = today.replace(day=1)
        end_date = today
    elif period in ("7d", "30d", "90d", "365d"):
        start_date = today - timedelta(days=int(period[:-1]) - 1)
        end_date = today
    elif period == "all":
        start_date = None
        end_date = None
    else:
        raise ApiError("Unknown report period '%s'." % period, field="period")

    if start_date and end_date and start_date > end_date:
        raise ApiError("The start date must come before the end date.", field="start_date")

    start = dates.day_start(start_date) if start_date else None
    end = dates.day_end(end_date) if end_date else None
    return start, end, start_date, end_date


def _completed(query):
    """Voided sales stay on record but never count towards totals."""
    return query.filter(Sale.status == SALE_COMPLETED)


def _in_range(query, start, end):
    if start:
        query = query.filter(Sale.created_at >= start)
    if end:
        query = query.filter(Sale.created_at <= end)
    return _completed(query)


def scoped_sales(start, end):
    query = Sale.query.filter(Sale.status == SALE_COMPLETED)
    if start:
        query = query.filter(Sale.created_at >= start)
    if end:
        query = query.filter(Sale.created_at <= end)
    return query


def sales_summary(start, end):
    base = scoped_sales(start, end).subquery()
    row = db.session.query(
        func.count(base.c.id),
        func.coalesce(func.sum(base.c.total), 0),
        func.coalesce(func.sum(base.c.discount), 0),
        func.coalesce(func.sum(base.c.tax), 0),
    ).one()
    count, revenue, discount, tax = row

    cost_row = _in_range(
        db.session.query(
            func.coalesce(func.sum(SaleItem.cost_price * SaleItem.quantity), 0)
        ).join(Sale, Sale.id == SaleItem.sale_id),
        start,
        end,
    )
    units_row = _in_range(
        db.session.query(func.coalesce(func.sum(SaleItem.quantity), 0)).join(
            Sale, Sale.id == SaleItem.sale_id
        ),
        start,
        end,
    )

    cost = Decimal(str(cost_row.scalar() or 0))
    units = int(units_row.scalar() or 0)
    revenue = Decimal(str(revenue or 0))
    average = revenue / count if count else ZERO

    return {
        "transactions": count,
        "revenue": money_str(revenue),
        "discount": money_str(Decimal(str(discount or 0))),
        "tax": money_str(Decimal(str(tax or 0))),
        "cost_of_goods": money_str(cost),
        "gross_profit": money_str(revenue - Decimal(str(tax or 0)) - cost),
        "average_sale": money_str(quantize(average)),
        "units_sold": units,
    }


def sales_trend(days=7):
    today = dates.today()
    first_day = today - timedelta(days=days - 1)
    rows = (
        _completed(db.session.query(Sale.created_at, Sale.total))
        .filter(Sale.created_at >= dates.day_start(first_day))
        .all()
    )
    # Bucketed here rather than with SQL date() so days follow the shop's clock.
    buckets = {}
    for created_at, total in rows:
        day = dates.local_date(created_at)
        count, revenue = buckets.get(day, (0, ZERO))
        buckets[day] = (count + 1, revenue + Decimal(str(total or 0)))
    trend = []
    for offset in range(days):
        day = first_day + timedelta(days=offset)
        count, revenue = buckets.get(day, (0, ZERO))
        trend.append(
            {"date": day.isoformat(), "transactions": count, "revenue": money_str(revenue)}
        )
    return trend


def product_performance(start, end, limit=None, order_by="units"):
    query = (
        db.session.query(
            SaleItem.product_id,
            SaleItem.product_name,
            SaleItem.product_sku,
            func.sum(SaleItem.quantity).label("units"),
            func.sum(SaleItem.subtotal).label("revenue"),
            func.sum(SaleItem.cost_price * SaleItem.quantity).label("cost"),
            func.count(func.distinct(SaleItem.sale_id)).label("transactions"),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .group_by(SaleItem.product_id, SaleItem.product_name, SaleItem.product_sku)
    )
    query = _in_range(query, start, end)

    sort = {
        "units": func.sum(SaleItem.quantity).desc(),
        "revenue": func.sum(SaleItem.subtotal).desc(),
        "profit": (
            func.sum(SaleItem.subtotal) - func.sum(SaleItem.cost_price * SaleItem.quantity)
        ).desc(),
    }.get(order_by, func.sum(SaleItem.quantity).desc())
    query = query.order_by(sort)
    if limit:
        query = query.limit(limit)

    results = []
    for row in query.all():
        revenue = Decimal(str(row.revenue or 0))
        cost = Decimal(str(row.cost or 0))
        results.append(
            {
                "product_id": row.product_id,
                "product_name": row.product_name,
                "product_sku": row.product_sku,
                "units_sold": int(row.units or 0),
                "revenue": money_str(revenue),
                "cost": money_str(cost),
                "gross_profit": money_str(revenue - cost),
                "transactions": int(row.transactions or 0),
            }
        )
    return results


def payment_breakdown(start, end):
    query = (
        db.session.query(
            Payment.payment_method,
            func.count(Payment.id),
            func.coalesce(func.sum(Payment.amount), 0),
        )
        .join(Sale, Sale.id == Payment.sale_id)
        .group_by(Payment.payment_method)
        .order_by(func.sum(Payment.amount).desc())
    )
    query = _in_range(query, start, end)
    return [
        {
            "payment_method": row[0],
            "transactions": row[1],
            "amount": money_str(Decimal(str(row[2] or 0))),
        }
        for row in query.all()
    ]


def inventory_summary():
    row = db.session.query(
        func.count(Product.id),
        func.coalesce(func.sum(Product.stock_quantity), 0),
        func.coalesce(
            func.sum(Product.stock_quantity * Product.cost_price), 0
        ),
        func.coalesce(
            func.sum(Product.stock_quantity * Product.selling_price), 0
        ),
        func.coalesce(
            func.sum(case((Product.stock_quantity <= 0, 1), else_=0)), 0
        ),
        func.coalesce(
            func.sum(
                case(
                    (
                        (Product.stock_quantity > 0)
                        & (Product.stock_quantity <= Product.low_stock_threshold),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ),
    ).filter(Product.is_active.is_(True)).one()

    return {
        "products": int(row[0] or 0),
        "units_in_stock": int(row[1] or 0),
        "stock_cost_value": money_str(Decimal(str(row[2] or 0))),
        "stock_retail_value": money_str(Decimal(str(row[3] or 0))),
        "out_of_stock": int(row[4] or 0),
        "low_stock": int(row[5] or 0),
    }


def low_stock_products(limit=10):
    return (
        Product.query.filter(
            Product.is_active.is_(True),
            Product.stock_quantity <= Product.low_stock_threshold,
        )
        .order_by(Product.stock_quantity.asc(), Product.name.asc())
        .limit(limit)
        .all()
    )


def category_performance(start, end):
    """Sales per category. Uncategorised items are grouped together."""
    query = (
        db.session.query(
            Category.id,
            Category.name,
            func.sum(SaleItem.quantity).label("units"),
            func.sum(SaleItem.subtotal).label("revenue"),
            func.sum(SaleItem.cost_price * SaleItem.quantity).label("cost"),
            func.count(func.distinct(SaleItem.sale_id)).label("transactions"),
        )
        .select_from(SaleItem)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .outerjoin(Product, Product.id == SaleItem.product_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .group_by(Category.id, Category.name)
        .order_by(func.sum(SaleItem.subtotal).desc())
    )
    query = _in_range(query, start, end)
    results = []
    for row in query.all():
        revenue = Decimal(str(row.revenue or 0))
        cost = Decimal(str(row.cost or 0))
        results.append(
            {
                "category_id": row[0],
                "category_name": row[1] or "Uncategorised",
                "units_sold": int(row.units or 0),
                "revenue": money_str(revenue),
                "cost": money_str(cost),
                "gross_profit": money_str(revenue - cost),
                "transactions": int(row.transactions or 0),
            }
        )
    return results


def cashier_performance(start, end):
    """Completed sales per staff member over the period."""
    query = (
        db.session.query(
            User.id,
            User.name,
            func.count(Sale.id).label("transactions"),
            func.coalesce(func.sum(Sale.total), 0).label("revenue"),
            func.coalesce(func.sum(Sale.discount), 0).label("discount"),
        )
        .join(Sale, Sale.cashier_id == User.id)
        .group_by(User.id, User.name)
        .order_by(func.sum(Sale.total).desc())
    )
    query = _in_range(query, start, end)
    voided = (
        db.session.query(Sale.cashier_id, func.count(Sale.id))
        .filter(Sale.status != SALE_COMPLETED)
    )
    if start:
        voided = voided.filter(Sale.created_at >= start)
    if end:
        voided = voided.filter(Sale.created_at <= end)
    voided_counts = dict(voided.group_by(Sale.cashier_id).all())

    results = []
    for row in query.all():
        revenue = Decimal(str(row.revenue or 0))
        count = int(row.transactions or 0)
        results.append(
            {
                "user_id": row[0],
                "name": row[1],
                "transactions": count,
                "revenue": money_str(revenue),
                "discount": money_str(Decimal(str(row.discount or 0))),
                "average_sale": money_str(quantize(revenue / count) if count else ZERO),
                "voided": int(voided_counts.get(row[0], 0)),
            }
        )
    return results
