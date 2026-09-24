import re

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from ..extensions import db
from ..models import (
    PIN_ROLES,
    ROLE_ADMIN,
    ROLE_CASHIER,
    ROLE_LABELS,
    ROLES,
    SALE_COMPLETED,
    ActivityLog,
    Business,
    Sale,
    User,
)
from ..permissions import ACTIVITY_VIEW, STAFF_MANAGE, can_manage_user
from ..utils import dates
from ..utils.activity import log_activity
from ..utils.auth import current_user, permission_required
from ..utils.errors import ApiError, Conflict, Forbidden, NotFound
from ..utils.money import money_str
from ..utils.pagination import paginate
from ..utils.validation import arg_int, get_bool, get_choice, get_str, payload

bp = Blueprint("users", __name__, url_prefix="/api/users")

USERNAME_PATTERN = re.compile(r"^[a-z0-9._-]{2,80}$")


def _assert_unique(field, value, user_id=None):
    column = getattr(User, field)
    query = User.query.filter(func.lower(column) == value.lower())
    if user_id:
        query = query.filter(User.id != user_id)
    if query.first():
        raise Conflict("That %s is already in use." % field, field=field)


def _clean_username(value):
    username = value.strip().lower()
    if not USERNAME_PATTERN.match(username):
        raise ApiError(
            "Use 2-80 letters, numbers, dots, dashes or underscores (no spaces).",
            field="username",
        )
    return username


def _clean_email(data):
    email = get_str(data, "email", max_length=160)
    if not email:
        return None
    email = email.lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise ApiError("Enter a valid email address.", field="email")
    return email


def _clean_password(data, key="password", required=True):
    password = get_str(data, key, required=required, max_length=200)
    if password is not None and len(password) < 8:
        raise ApiError("The password must be at least 8 characters.", field=key)
    return password


def validate_new_account(data, role):
    """Shared by staff creation and first-run setup."""
    from .auth import validate_pin

    account = {
        "name": get_str(data, "name", required=True, max_length=120),
        "username": _clean_username(get_str(data, "username", required=True, max_length=80)),
        "email": _clean_email(data),
        "phone": get_str(data, "phone", max_length=40),
        "password": _clean_password(data),
        "pin": None,
    }
    pin = get_str(data, "pin", max_length=6)
    if pin:
        if role not in PIN_ROLES:
            raise ApiError("Only cashiers and managers can sign in with a PIN.", field="pin")
        account["pin"] = validate_pin(pin)
    _assert_unique("username", account["username"])
    if account["email"]:
        _assert_unique("email", account["email"])
    return account


def _sales_today(user_ids):
    if not user_ids:
        return {}
    today = dates.today()
    rows = (
        db.session.query(Sale.cashier_id, func.count(Sale.id), func.sum(Sale.total))
        .filter(
            Sale.cashier_id.in_(user_ids),
            Sale.status == SALE_COMPLETED,
            Sale.created_at >= dates.day_start(today),
            Sale.created_at <= dates.day_end(today),
        )
        .group_by(Sale.cashier_id)
        .all()
    )
    return {row[0]: (row[1], row[2]) for row in rows}


def _staff_dict(user, sales=None):
    data = user.to_dict()
    count, total = (sales or {}).get(user.id, (0, 0))
    data["sales_today"] = {"count": count, "total": money_str(total or 0)}
    return data


def _get_manageable(user_id):
    actor = current_user()
    user = db.session.get(User, user_id)
    if user is None:
        raise NotFound("That staff member could not be found.")
    if user.id != actor.id and not can_manage_user(actor, user.role):
        raise Forbidden("Only the owner can change %s accounts." % ROLE_LABELS[user.role])
    return user


@bp.get("/roles")
@permission_required(STAFF_MANAGE)
def roles():
    actor = current_user()
    return jsonify(
        {
            "items": [
                {"value": role, "label": ROLE_LABELS[role], "pin": role in PIN_ROLES}
                for role in ROLES
                if can_manage_user(actor, role)
            ]
        }
    )


@bp.get("")
@permission_required(STAFF_MANAGE)
def list_users():
    query = User.query
    if request.args.get("status") == "disabled":
        query = query.filter(User.is_active.is_(False))
    elif request.args.get("status") == "active":
        query = query.filter(User.is_active.is_(True))
    role = request.args.get("role")
    if role in ROLES:
        query = query.filter(User.role == role)
    query = query.order_by(User.is_active.desc(), User.name.asc())
    page, meta = paginate(query)
    sales = _sales_today([u.id for u in page.items])
    return jsonify({"items": [_staff_dict(u, sales) for u in page.items], "pagination": meta})


@bp.get("/<int:user_id>")
@permission_required(STAFF_MANAGE)
def get_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        raise NotFound("That staff member could not be found.")
    return jsonify({"user": _staff_dict(user, _sales_today([user.id]))})


@bp.post("")
@permission_required(STAFF_MANAGE)
def create_user():
    actor = current_user()
    data = payload()
    role = get_choice(data, "role", ROLES, default=ROLE_CASHIER)
    if not can_manage_user(actor, role):
        raise Forbidden("Only the owner can create %s accounts." % ROLE_LABELS[role])
    account = validate_new_account(data, role)

    user = User(
        business_id=Business.current_id(),
        name=account["name"],
        username=account["username"],
        email=account["email"],
        phone=account["phone"],
        role=role,
    )
    user.set_password(account["password"])
    if account["pin"]:
        user.set_pin(account["pin"])
    db.session.add(user)
    db.session.flush()
    log_activity(
        actor,
        "user.created",
        "user",
        user.id,
        "Created %s account for %s" % (ROLE_LABELS[role], user.name),
    )
    db.session.commit()
    return jsonify({"user": _staff_dict(user)}), 201


@bp.patch("/<int:user_id>")
@permission_required(STAFF_MANAGE)
def update_user(user_id):
    from .auth import validate_pin

    actor = current_user()
    user = _get_manageable(user_id)
    data = payload()

    name = get_str(data, "name", max_length=120)
    if name:
        user.name = name

    if "username" in data:
        username = _clean_username(get_str(data, "username", required=True, max_length=80))
        _assert_unique("username", username, user.id)
        user.username = username

    if "email" in data:
        email = _clean_email(data)
        if email:
            _assert_unique("email", email, user.id)
        user.email = email

    if "phone" in data:
        user.phone = get_str(data, "phone", max_length=40)

    if "role" in data:
        role = get_choice(data, "role", ROLES, required=True)
        if role != user.role:
            if user.id == actor.id:
                raise ApiError("You cannot change your own role.", field="role")
            if not can_manage_user(actor, role):
                raise Forbidden("Only the owner can give out the %s role." % ROLE_LABELS[role])
            if user.role == ROLE_ADMIN and _last_active_owner(user):
                raise ApiError("Keep at least one active owner account.", field="role")
            log_activity(
                actor,
                "user.role_changed",
                "user",
                user.id,
                "%s: %s to %s" % (user.name, ROLE_LABELS[user.role], ROLE_LABELS[role]),
            )
            user.role = role
            if role not in PIN_ROLES:
                user.pin_hash = None

    if "is_active" in data:
        is_active = bool(get_bool(data, "is_active", default=True))
        if is_active != user.is_active:
            if user.id == actor.id and not is_active:
                raise ApiError("You cannot disable your own account.", field="is_active")
            if not is_active and user.role == ROLE_ADMIN and _last_active_owner(user):
                raise ApiError("Keep at least one active owner account.", field="is_active")
            user.is_active = is_active
            log_activity(
                actor,
                "user.enabled" if is_active else "user.disabled",
                "user",
                user.id,
                "%s %s" % ("Reactivated" if is_active else "Disabled", user.name),
            )

    if "password" in data:
        user.set_password(_clean_password(data))
        log_activity(
            actor, "user.password_reset", "user", user.id, "Reset password for %s" % user.name
        )

    if "pin" in data:
        pin = get_str(data, "pin", max_length=6)
        if pin:
            if user.role not in PIN_ROLES:
                raise ApiError("Only cashiers and managers can sign in with a PIN.", field="pin")
            user.set_pin(validate_pin(pin))
            log_activity(actor, "user.pin_reset", "user", user.id, "Set PIN for %s" % user.name)
        else:
            user.pin_hash = None
            log_activity(
                actor, "user.pin_removed", "user", user.id, "Removed PIN for %s" % user.name
            )

    log_activity(actor, "user.updated", "user", user.id, "Updated %s" % user.name)
    db.session.commit()
    return jsonify({"user": _staff_dict(user, _sales_today([user.id]))})


def _last_active_owner(user):
    return (
        User.query.filter(
            User.role == ROLE_ADMIN, User.is_active.is_(True), User.id != user.id
        ).count()
        == 0
    )


@bp.get("/activity")
@permission_required(ACTIVITY_VIEW)
def activity():
    query = ActivityLog.query
    user_id = arg_int("user_id")
    if user_id:
        query = query.filter(ActivityLog.user_id == user_id)
    if request.args.get("action"):
        query = query.filter(ActivityLog.action == request.args["action"])
    query = query.order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
    page, meta = paginate(query)
    return jsonify({"items": [a.to_dict() for a in page.items], "pagination": meta})
