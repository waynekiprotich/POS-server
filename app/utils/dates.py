"""Calendar days in the shop's timezone, as UTC bounds for database queries."""
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import current_app, g, has_request_context


def valid_timezone(name):
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def business_tz():
    """The shop's timezone from Settings, falling back to BUSINESS_TIMEZONE."""
    if has_request_context() and "business_tz" in g:
        return g.business_tz
    from ..models import Setting

    name = Setting.get("timezone") or current_app.config["BUSINESS_TIMEZONE"]
    if not valid_timezone(name):
        name = current_app.config["BUSINESS_TIMEZONE"]
    tz = ZoneInfo(name)
    if has_request_context():
        g.business_tz = tz
    return tz


def today():
    return datetime.now(business_tz()).date()


def day_start(day):
    """First instant of a local calendar day, in UTC."""
    return datetime.combine(day, time.min, tzinfo=business_tz()).astimezone(timezone.utc)


def day_end(day):
    """Last instant of a local calendar day, in UTC."""
    return datetime.combine(day, time.max, tzinfo=business_tz()).astimezone(timezone.utc)


def local_date(value):
    """The local calendar day of a stored timestamp (SQLite returns it naive, in UTC)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(business_tz()).date()
