from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from .errors import ApiError

CENTS = Decimal("0.01")


def to_decimal(value, field=None, default=None):
    """Parse a money value without going through binary floats."""
    if value is None or value == "":
        if default is not None:
            return default
        raise ApiError("A value is required.", field=field)
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        amount = None
    if amount is None or not amount.is_finite():
        raise ApiError("'%s' is not a valid amount." % value, field=field)
    return amount


def quantize(value):
    return Decimal(value).quantize(CENTS, rounding=ROUND_HALF_UP)


def money_str(value):
    if value is None:
        return None
    return str(quantize(value))
