"""
First-run setup: creates the business, the owner account and the settings.

Only works while no business has finished setup, so once the shop is running
this endpoint refuses every request and cannot be used to add a second owner.
"""
from flask import Blueprint, jsonify

from ..extensions import db
from ..models import ROLE_ADMIN, Business, Category, Setting, User, utcnow
from ..utils.activity import log_activity
from ..utils.errors import ApiError, Conflict
from ..utils.validation import get_str, payload
from .settings import validate_settings
from .users import validate_new_account

bp = Blueprint("setup", __name__, url_prefix="/api/setup")

SETTING_FIELDS = (
    "business_address",
    "business_phone",
    "business_email",
    "business_tax_pin",
    "currency",
    "currency_symbol",
    "timezone",
    "tax_enabled",
    "tax_rate",
    "receipt_footer",
    "receipt_width",
)


@bp.get("/status")
def status():
    business = Business.current()
    ready = bool(business and business.setup_completed_at)
    return jsonify(
        {
            "setup_required": not ready,
            # Settings hold the name the owner edits; show the same one here.
            "business_name": Setting.get("business_name") if ready else None,
        }
    )


@bp.post("")
def complete_setup():
    if Business.setup_completed():
        raise Conflict("This POS has already been set up. Sign in instead.")

    data = payload()
    business_name = get_str(data, "business_name", required=True, max_length=160)
    owner = data.get("owner")
    if not isinstance(owner, dict):
        raise ApiError("Enter the owner's account details.", field="owner")
    account = validate_new_account(owner, role=ROLE_ADMIN)

    settings = {key: data[key] for key in SETTING_FIELDS if key in data}
    settings["business_name"] = business_name
    cleaned = validate_settings(settings)

    # Tables are created by migrations; an install that skipped them still works.
    business = Business.current()
    if business is None:
        business = Business(name=business_name)
        db.session.add(business)
    business.name = business_name
    db.session.flush()

    # Any accounts left from before setup (e.g. a failed attempt) would be an
    # unexplained back door; refuse rather than guess.
    if User.query.count():
        raise Conflict(
            "Staff accounts already exist in this database. Sign in, or restore "
            "a fresh database before running setup."
        )

    user = User(
        business_id=business.id,
        name=account["name"],
        username=account["username"],
        email=account["email"],
        phone=account["phone"],
        role=ROLE_ADMIN,
    )
    user.set_password(account["password"])
    db.session.add(user)

    Setting.set_many(cleaned)
    Category.query.filter(Category.business_id.is_(None)).update(
        {"business_id": business.id}, synchronize_session=False
    )
    business.setup_completed_at = utcnow()
    db.session.flush()
    log_activity(user, "setup.completed", "business", business.id, "Set up %s" % business_name)
    db.session.commit()
    return jsonify({"business": {"id": business.id, "name": business.name}}), 201
