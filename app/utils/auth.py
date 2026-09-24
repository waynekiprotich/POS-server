from functools import wraps

from flask import g
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from ..extensions import db
from ..models import ROLE_ADMIN, User
from ..permissions import has_permission
from .errors import Forbidden, Unauthorized


def load_current_user():
    """Resolve the JWT identity into a live, enabled user.

    The role is read from the database on every request, never from the token,
    so a demotion or a disabled account takes effect immediately.
    """
    verify_jwt_in_request()
    identity = get_jwt_identity()
    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        user_id = None
    user = db.session.get(User, user_id) if user_id is not None else None
    if user is None:
        raise Unauthorized("Your session is no longer valid. Please sign in again.")
    if not user.is_active:
        raise Unauthorized("This account has been disabled. Contact the owner.")
    g.current_user = user
    return user


def auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        load_current_user()
        return fn(*args, **kwargs)

    return wrapper


def permission_required(permission):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = load_current_user()
            if not has_permission(user, permission):
                raise Forbidden("You do not have permission to perform this action.")
            return fn(*args, **kwargs)

        return wrapper

    return decorator


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


def current_can(permission):
    return has_permission(current_user(), permission)
