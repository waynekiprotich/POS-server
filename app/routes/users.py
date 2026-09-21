from flask import Blueprint, jsonify, request
from sqlalchemy import func

from ..extensions import db
from ..models import ROLES, ActivityLog, User
from ..utils.activity import log_activity
from ..utils.auth import admin_required, current_user
from ..utils.errors import ApiError, Conflict, NotFound
from ..utils.pagination import paginate
from ..utils.validation import arg_int, get_bool, get_choice, get_str, payload

bp = Blueprint("users", __name__, url_prefix="/api/users")


def _assert_unique(field, value, user_id=None):
    column = getattr(User, field)
    query = User.query.filter(func.lower(column) == value.lower())
    if user_id:
        query = query.filter(User.id != user_id)
    if query.first():
        raise Conflict("That %s is already in use." % field, field=field)


@bp.get("")
@admin_required
def list_users():
    query = User.query
    if request.args.get("status") == "disabled":
        query = query.filter(User.is_active.is_(False))
    elif request.args.get("status") == "active":
        query = query.filter(User.is_active.is_(True))
    query = query.order_by(User.name.asc())
    page, meta = paginate(query)
    return jsonify({"items": [u.to_dict() for u in page.items], "pagination": meta})


@bp.post("")
@admin_required
def create_user():
    data = payload()
    name = get_str(data, "name", required=True, max_length=120)
    username = get_str(data, "username", required=True, max_length=80).lower()
    email = get_str(data, "email", required=True, max_length=160).lower()
    password = get_str(data, "password", required=True, max_length=200)
    role = get_choice(data, "role", ROLES, default="cashier")

    if "@" not in email or "." not in email.split("@")[-1]:
        raise ApiError("Enter a valid email address.", field="email")
    if len(password) < 8:
        raise ApiError("The password must be at least 8 characters.", field="password")

    _assert_unique("username", username)
    _assert_unique("email", email)

    user = User(name=name, username=username, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    log_activity(
        current_user(), "user.created", "user", user.id, "Created %s account for %s" % (role, name)
    )
    db.session.commit()
    return jsonify({"user": user.to_dict()}), 201


@bp.patch("/<int:user_id>")
@admin_required
def update_user(user_id):
    actor = current_user()
    user = db.session.get(User, user_id)
    if user is None:
        raise NotFound("That user could not be found.")
    data = payload()

    name = get_str(data, "name", max_length=120)
    if name:
        user.name = name

    if "username" in data:
        username = get_str(data, "username", required=True, max_length=80).lower()
        _assert_unique("username", username, user.id)
        user.username = username

    if "email" in data:
        email = get_str(data, "email", required=True, max_length=160).lower()
        _assert_unique("email", email, user.id)
        user.email = email

    if "role" in data:
        role = get_choice(data, "role", ROLES, required=True)
        if user.id == actor.id and role != actor.role:
            raise ApiError("You cannot change your own role.", field="role")
        user.role = role

    if "is_active" in data:
        is_active = bool(get_bool(data, "is_active", default=True))
        if user.id == actor.id and not is_active:
            raise ApiError("You cannot disable your own account.", field="is_active")
        user.is_active = is_active
        log_activity(
            actor,
            "user.enabled" if is_active else "user.disabled",
            "user",
            user.id,
            "%s %s" % ("Enabled" if is_active else "Disabled", user.name),
        )

    if "password" in data:
        password = get_str(data, "password", required=True, max_length=200)
        if len(password) < 8:
            raise ApiError("The password must be at least 8 characters.", field="password")
        user.set_password(password)
        log_activity(actor, "user.password_reset", "user", user.id, "Reset password for %s" % user.name)

    log_activity(actor, "user.updated", "user", user.id, "Updated %s" % user.name)
    db.session.commit()
    return jsonify({"user": user.to_dict()})


@bp.get("/activity")
@admin_required
def activity():
    query = ActivityLog.query
    if request.args.get("user_id"):
        query = query.filter(ActivityLog.user_id == arg_int("user_id"))
    if request.args.get("action"):
        query = query.filter(ActivityLog.action == request.args["action"])
    query = query.order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
    page, meta = paginate(query)
    return jsonify({"items": [a.to_dict() for a in page.items], "pagination": meta})
