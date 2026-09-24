import math

from flask import Blueprint, jsonify

from ..extensions import db
from ..models import DEFAULT_SETTINGS, Setting
from ..models.setting import RECEIPT_WIDTHS
from ..permissions import SETTINGS_MANAGE, has_permission
from ..utils.activity import log_activity
from ..utils.auth import auth_required, current_user, permission_required
from ..utils.dates import valid_timezone
from ..utils.errors import ApiError
from ..utils.validation import payload

bp = Blueprint("settings", __name__, url_prefix="/api/settings")

# What every signed-in till needs: receipt layout, prices, tax and idle rules.
PUBLIC_KEYS = (
    "business_name",
    "business_address",
    "business_phone",
    "business_email",
    "business_tax_pin",
    "currency",
    "currency_symbol",
    "receipt_footer",
    "receipt_width",
    "receipt_show_cashier",
    "tax_enabled",
    "tax_rate",
    "timezone",
    "idle_logout_minutes",
)

BOOLEAN_KEYS = (
    "tax_enabled",
    "allow_negative_stock",
    "receipt_show_cashier",
    "pin_login_enabled",
    "cashiers_see_costs",
    "auto_backup_enabled",
)

MAX_LENGTH = 500


def _whole_number(data, key, minimum, maximum, label):
    try:
        value = int(str(data[key]).strip())
    except (TypeError, ValueError):
        raise ApiError("%s must be a whole number." % label, field=key)
    if value < minimum or value > maximum:
        raise ApiError(
            "%s must be between %d and %d." % (label, minimum, maximum), field=key
        )
    return str(value)


def validate_settings(data):
    """Check and normalise a settings update; returns the cleaned values."""
    unknown = [k for k in data if k not in DEFAULT_SETTINGS]
    if unknown:
        raise ApiError("Unknown setting: %s." % ", ".join(sorted(unknown)))

    cleaned = {}
    for key, value in data.items():
        text = "" if value is None else str(value).strip()
        if len(text) > MAX_LENGTH:
            raise ApiError("That value is too long.", field=key)
        cleaned[key] = text

    if "tax_rate" in cleaned:
        try:
            rate = float(cleaned["tax_rate"] or 0)
        except ValueError:
            raise ApiError("The tax rate must be a number.", field="tax_rate")
        if not math.isfinite(rate) or rate < 0 or rate > 100:
            raise ApiError("The tax rate must be between 0 and 100.", field="tax_rate")
        cleaned["tax_rate"] = cleaned["tax_rate"] or "0"

    for key in BOOLEAN_KEYS:
        if key in data:
            raw = data[key]
            truthy = raw is True or str(raw).lower() in ("1", "true", "yes", "on")
            cleaned[key] = "true" if truthy else "false"

    if "timezone" in cleaned and not valid_timezone(cleaned["timezone"]):
        raise ApiError(
            "Choose a timezone such as Africa/Nairobi.", field="timezone"
        )
    if "receipt_width" in cleaned and cleaned["receipt_width"] not in RECEIPT_WIDTHS:
        raise ApiError(
            "Receipt width must be one of: %s." % ", ".join(RECEIPT_WIDTHS),
            field="receipt_width",
        )
    if "currency" in cleaned:
        if not cleaned["currency"]:
            raise ApiError("Enter a currency code such as KES.", field="currency")
        cleaned["currency"] = cleaned["currency"].upper()[:8]
    if "business_name" in cleaned and not cleaned["business_name"]:
        raise ApiError("The business name cannot be empty.", field="business_name")
    if "default_low_stock_threshold" in cleaned:
        cleaned["default_low_stock_threshold"] = _whole_number(
            cleaned, "default_low_stock_threshold", 0, 100000, "Low stock level"
        )
    if "idle_logout_minutes" in cleaned:
        cleaned["idle_logout_minutes"] = _whole_number(
            cleaned, "idle_logout_minutes", 0, 720, "Idle sign-out"
        )
    if "backup_retention" in cleaned:
        cleaned["backup_retention"] = _whole_number(
            cleaned, "backup_retention", 1, 365, "Backups to keep"
        )
    return cleaned


@bp.get("")
@auth_required
def get_settings():
    values = Setting.as_dict()
    if not has_permission(current_user(), SETTINGS_MANAGE):
        values = {k: v for k, v in values.items() if k in PUBLIC_KEYS}
    return jsonify({"settings": values})


@bp.patch("")
@permission_required(SETTINGS_MANAGE)
def update_settings():
    cleaned = validate_settings(payload())
    Setting.set_many(cleaned)
    if "business_name" in cleaned:
        from ..models import Business

        business = Business.current()
        if business is not None:
            business.name = cleaned["business_name"]
    log_activity(
        current_user(),
        "settings.updated",
        "setting",
        None,
        "Updated settings: %s" % ", ".join(sorted(cleaned.keys())),
    )
    db.session.commit()
    return jsonify({"settings": Setting.as_dict()})
