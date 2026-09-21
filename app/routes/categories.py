from flask import Blueprint, jsonify, request
from sqlalchemy import func

from ..extensions import db
from ..models import Category
from ..utils.activity import log_activity
from ..utils.auth import admin_required, auth_required, current_user
from ..utils.errors import Conflict, NotFound
from ..utils.validation import get_bool, get_str, payload

bp = Blueprint("categories", __name__, url_prefix="/api/categories")


def _assert_name_free(name, category_id=None):
    query = Category.query.filter(func.lower(Category.name) == name.lower())
    if category_id:
        query = query.filter(Category.id != category_id)
    if query.first():
        raise Conflict("A category named '%s' already exists." % name, field="name")


@bp.get("")
@auth_required
def list_categories():
    query = Category.query
    if request.args.get("include_inactive") != "true":
        query = query.filter(Category.is_active.is_(True))
    items = query.order_by(Category.name.asc()).all()
    return jsonify({"items": [c.to_dict() for c in items]})


@bp.post("")
@admin_required
def create_category():
    data = payload()
    name = get_str(data, "name", required=True, max_length=120)
    _assert_name_free(name)
    category = Category(
        name=name, description=get_str(data, "description", max_length=255)
    )
    db.session.add(category)
    db.session.flush()
    log_activity(
        current_user(), "category.created", "category", category.id, "Created category %s" % name
    )
    db.session.commit()
    return jsonify({"category": category.to_dict()}), 201


@bp.patch("/<int:category_id>")
@admin_required
def update_category(category_id):
    category = db.session.get(Category, category_id)
    if category is None:
        raise NotFound("That category could not be found.")
    data = payload()
    name = get_str(data, "name", max_length=120)
    if name:
        _assert_name_free(name, category.id)
        category.name = name
    if "description" in data:
        category.description = get_str(data, "description", max_length=255)
    if "is_active" in data:
        category.is_active = bool(get_bool(data, "is_active", default=True))
    log_activity(
        current_user(),
        "category.updated",
        "category",
        category.id,
        "Updated category %s" % category.name,
    )
    db.session.commit()
    return jsonify({"category": category.to_dict()})
