import time
from collections import defaultdict

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
)
from sqlalchemy import func

from ..extensions import db
from ..models import User
from ..utils.activity import log_activity
from ..utils.auth import auth_required, current_user, load_current_user
from ..utils.errors import ApiError, Unauthorized
from ..utils.validation import get_str, payload

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

_attempts = defaultdict(list)


def _rate_limit_key():
    # remote_addr already reflects trusted proxies (TRUSTED_PROXY_COUNT); the raw
    # X-Forwarded-For header is client-controlled and would let anyone reset
    # their limit by changing it.
    return request.remote_addr or "unknown"


def _check_rate_limit():
    window = current_app.config["LOGIN_RATE_WINDOW_SECONDS"]
    limit = current_app.config["LOGIN_RATE_LIMIT"]
    key = _rate_limit_key()
    now = time.time()
    hits = [t for t in _attempts[key] if now - t < window]
    _attempts[key] = hits
    if len(hits) >= limit:
        raise ApiError(
            "Too many sign-in attempts. Please wait a few minutes and try again.",
            status_code=429,
        )


def _record_attempt():
    _attempts[_rate_limit_key()].append(time.time())


def _tokens(user):
    identity = str(user.id)
    claims = {"role": user.role, "name": user.name}
    return {
        "access_token": create_access_token(identity=identity, additional_claims=claims),
        "refresh_token": create_refresh_token(identity=identity),
    }


@bp.post("/login")
def login():
    _check_rate_limit()
    data = payload()
    identifier = get_str(data, "identifier", required=True, max_length=160)
    password = get_str(data, "password", required=True, max_length=200)

    user = User.query.filter(
        (func.lower(User.username) == identifier.lower())
        | (func.lower(User.email) == identifier.lower())
    ).first()

    if user is None or not user.check_password(password):
        _record_attempt()
        raise Unauthorized("Incorrect username or password.")
    if not user.is_active:
        _record_attempt()
        raise Unauthorized("This account has been disabled. Contact an administrator.")

    log_activity(user, "user.login", "user", user.id, "%s signed in" % user.name)
    db.session.commit()
    return jsonify({"user": user.to_dict(), **_tokens(user)})


@bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None or not user.is_active:
        raise Unauthorized("Your session is no longer valid. Please sign in again.")
    return jsonify(
        {
            "user": user.to_dict(),
            "access_token": create_access_token(
                identity=str(user.id),
                additional_claims={"role": user.role, "name": user.name},
            ),
        }
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
