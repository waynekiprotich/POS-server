from functools import wraps

from flask import g
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from ..extensions import db
from ..models import ROLE_ADMIN, User
from .errors import Forbidden, Unauthorized


def load_current_user():
    """Resolve the JWT identity into a live, enabled user."""
    verify_jwt_in_request()
    identity = get_jwt_identity()
    user = db.session.get(User, int(identity)) if identity is not None else None
    if user is None:
        raise Unauthorized("Your session is no longer valid. Please sign in again.")
    if not user.is_active:
        raise Forbidden("This account has been disabled.")
    g.current_user = user
    return user


def auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        load_current_user()
        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = load_current_user()
        if user.role != ROLE_ADMIN:
            raise Forbidden("You do not have permission to perform this action.")
        return fn(*args, **kwargs)

    return wrapper


def current_user():
    return getattr(g, "current_user", None)
