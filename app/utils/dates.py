"""Calendar days in the shop's timezone, as UTC bounds for database queries."""
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from flask import current_app


def business_tz():
    return ZoneInfo(current_app.config["BUSINESS_TIMEZONE"])


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
