import re

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
)
from sqlalchemy import func

from ..extensions import db
from ..models import PIN_ROLES, Setting, User, utcnow
from ..utils.activity import log_activity
from ..utils.auth import auth_required, current_user
from ..utils.errors import ApiError, Unauthorized
from ..utils.initials import initials
from ..utils.rate_limit import limiter
from ..utils.validation import get_int, get_str, payload

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

PIN_PATTERN = re.compile(r"^\d{4,6}$")
TOO_MANY = "Too many sign-in attempts. Please wait a few minutes and try again."


def _client_key():
    # remote_addr already reflects trusted proxies (TRUSTED_PROXY_COUNT); the raw
    # X-Forwarded-For header is client-controlled and would let anyone reset
    # their limit by changing it.
    return request.remote_addr or "unknown"


def _window():
    return current_app.config["LOGIN_RATE_WINDOW_SECONDS"]


def _tokens(user):
    identity = str(user.id)
    return {
        "access_token": create_access_token(identity=identity),
        "refresh_token": create_refresh_token(identity=identity),
    }


def _signed_in(user, method):
    user.last_login_at = utcnow()
    log_activity(
        user, "user.login", "user", user.id, "%s signed in (%s)" % (user.name, method)
    )
    db.session.commit()
    return jsonify({"user": user.to_dict(), **_tokens(user)})


def validate_pin(pin, field="pin"):
    if not pin or not PIN_PATTERN.match(pin):
        raise ApiError("The PIN must be 4 to 6 digits.", field=field)
    return pin


@bp.post("/login")
def login():
    ip_key = "login:%s" % _client_key()
    limiter.check(ip_key, current_app.config["LOGIN_RATE_LIMIT"], _window(), TOO_MANY)
    data = payload()
    identifier = get_str(data, "identifier", required=True, max_length=160)
    password = get_str(data, "password", required=True, max_length=200)

    user = User.query.filter(
        (func.lower(User.username) == identifier.lower())
        | (func.lower(User.email) == identifier.lower())
    ).first()

    if user is None or not user.check_password(password):
        limiter.record(ip_key)
        raise Unauthorized("Incorrect username or password.")
    if not user.is_active:
        limiter.record(ip_key)
        raise Unauthorized("This account has been disabled. Contact the owner.")
    return _signed_in(user, "password")


@bp.get("/pin-users")
def pin_users():
    """Who can tap in with a PIN on this till. Names only, no other details."""
    if Setting.get("pin_login_enabled") != "true":
        return jsonify({"enabled": False, "items": []})
    users = (
        User.query.filter(
            User.is_active.is_(True),
            User.pin_hash.isnot(None),
            User.role.in_(PIN_ROLES),
        )
        .order_by(User.name.asc())
        .all()
    )
    return jsonify(
        {
            "enabled": True,
            "items": [{"id": u.id, "name": u.name, "initials": initials(u.name)} for u in users],
        }
    )


@bp.post("/pin-login")
def pin_login():
    if Setting.get("pin_login_enabled") != "true":
        raise ApiError("PIN sign-in is turned off. Use your password.", status_code=403)
    ip_key = "login:%s" % _client_key()
    limiter.check(ip_key, current_app.config["LOGIN_RATE_LIMIT"], _window(), TOO_MANY)

    data = payload()
    user_id = get_int(data, "user_id", required=True)
    pin = get_str(data, "pin", required=True, max_length=6)
    user_key = "pin:%s" % user_id
    limiter.check(
        user_key,
        current_app.config["PIN_ATTEMPT_LIMIT"],
        _window(),
        "Too many wrong PINs for this account. Wait a few minutes or sign in "
        "with your password.",
    )

    user = db.session.get(User, user_id)
    if user is None or not user.can_use_pin or not user.check_pin(pin):
        limiter.record(ip_key)
        limiter.record(user_key)
        raise Unauthorized("Incorrect PIN.")
    if not user.is_active:
        raise Unauthorized("This account has been disabled. Contact the owner.")
    limiter.reset(user_key)
    return _signed_in(user, "PIN")


@bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    try:
        user = db.session.get(User, int(get_jwt_identity()))
    except (TypeError, ValueError):
        user = None
    if user is None or not user.is_active:
        raise Unauthorized("Your session is no longer valid. Please sign in again.")
    return jsonify(
        {"user": user.to_dict(), "access_token": create_access_token(identity=str(user.id))}
    )


@bp.get("/me")
@auth_required
def me():
    return jsonify({"user": current_user().to_dict()})


@bp.post("/logout")
@auth_required
def logout():
    user = current_user()
    log_activity(user, "user.logout", "user", user.id, "%s signed out" % user.name)
    db.session.commit()
    return jsonify({"message": "Signed out."})


@bp.post("/change-password")
@auth_required
def change_password():
    user = current_user()
    data = payload()
    old = get_str(data, "current_password", required=True, max_length=200)
    new = get_str(data, "new_password", required=True, max_length=200)
    if not user.check_password(old):
        raise ApiError("Your current password is incorrect.", field="current_password")
    if len(new) < 8:
        raise ApiError(
            "The new password must be at least 8 characters.", field="new_password"
        )
    user.set_password(new)
    log_activity(user, "user.password_changed", "user", user.id, "Password changed")
    db.session.commit()
    return jsonify({"message": "Password updated."})


@bp.post("/change-pin")
@auth_required
def change_pin():
    """Staff set their own PIN, confirming with their password."""
    user = current_user()
    data = payload()
    password = get_str(data, "current_password", required=True, max_length=200)
    if not user.check_password(password):
        raise ApiError("Your password is incorrect.", field="current_password")
    if user.role not in PIN_ROLES:
        raise ApiError("Owner accounts sign in with a password only.", field="pin")
    user.set_pin(validate_pin(get_str(data, "pin", required=True, max_length=6)))
    log_activity(user, "user.pin_changed", "user", user.id, "PIN changed")
    db.session.commit()
    return jsonify({"user": user.to_dict()})
