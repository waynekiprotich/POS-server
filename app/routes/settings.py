import math

from flask import Blueprint, jsonify

from ..extensions import db
from ..models import DEFAULT_SETTINGS, Setting
from ..utils.activity import log_activity
from ..utils.auth import admin_required, auth_required, current_user
from ..utils.errors import ApiError
from ..utils.validation import payload

bp = Blueprint("settings", __name__, url_prefix="/api/settings")

PUBLIC_KEYS = (
    "business_name",
    "business_address",
    "business_phone",
    "business_email",
    "currency",
    "currency_symbol",
    "receipt_footer",
    "tax_enabled",
    "tax_rate",
)


@bp.get("")
@auth_required
def get_settings():
    values = Setting.as_dict()
    if not current_user().is_admin:
        values = {k: v for k, v in values.items() if k in PUBLIC_KEYS}
    return jsonify({"settings": values})


@bp.patch("")
@admin_required
def update_settings():
    data = payload()
    unknown = [k for k in data if k not in DEFAULT_SETTINGS]
    if unknown:
        raise ApiError("Unknown setting: %s." % ", ".join(sorted(unknown)))

    if "tax_rate" in data:
        try:
            rate = float(data["tax_rate"])
        except (TypeError, ValueError):
            raise ApiError("The tax rate must be a number.", field="tax_rate")
        if not math.isfinite(rate) or rate < 0 or rate > 100:
            raise ApiError("The tax rate must be between 0 and 100.", field="tax_rate")

    for key in ("tax_enabled", "allow_negative_stock"):
        if key in data:
            data[key] = "true" if str(data[key]).lower() in ("1", "true", "yes", "on") else "false"

    Setting.set_many(data)
    log_activity(
        current_user(),
        "settings.updated",
        "setting",
        None,
        "Updated settings: %s" % ", ".join(sorted(data.keys())),
    )
    db.session.commit()
    return jsonify({"settings": Setting.as_dict()})
