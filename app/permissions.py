"""
Role-based permissions, enforced by Flask on every protected endpoint.

The browser receives the same list (on /api/auth/me) only to decide what to
show; hiding a button is never the security boundary.
"""
from .models.user import ROLE_ADMIN, ROLE_CASHIER, ROLE_MANAGER, ROLE_VIEWER

POS_SELL = "pos.sell"
DISCOUNT_APPLY = "discount.apply"
SALES_VIEW_ALL = "sales.view_all"
SALES_VOID = "sales.void"
PRODUCTS_MANAGE = "products.manage"
INVENTORY_VIEW = "inventory.view"
INVENTORY_MANAGE = "inventory.manage"
REPORTS_VIEW = "reports.view"
COSTS_VIEW = "costs.view"
STAFF_MANAGE = "staff.manage"
ACTIVITY_VIEW = "activity.view"
SETTINGS_MANAGE = "settings.manage"
BACKUPS_MANAGE = "backups.manage"

ALL_PERMISSIONS = frozenset(
    {
        POS_SELL,
        DISCOUNT_APPLY,
        SALES_VIEW_ALL,
        SALES_VOID,
        PRODUCTS_MANAGE,
        INVENTORY_VIEW,
        INVENTORY_MANAGE,
        REPORTS_VIEW,
        COSTS_VIEW,
        STAFF_MANAGE,
        ACTIVITY_VIEW,
        SETTINGS_MANAGE,
        BACKUPS_MANAGE,
    }
)

ROLE_PERMISSIONS = {
    ROLE_ADMIN: ALL_PERMISSIONS,
    ROLE_MANAGER: frozenset(
        {
            POS_SELL,
            DISCOUNT_APPLY,
            SALES_VIEW_ALL,
            PRODUCTS_MANAGE,
            INVENTORY_VIEW,
            INVENTORY_MANAGE,
            REPORTS_VIEW,
            COSTS_VIEW,
            # Limited: managers may only manage cashier and viewer accounts.
            STAFF_MANAGE,
            ACTIVITY_VIEW,
        }
    ),
    ROLE_CASHIER: frozenset({POS_SELL}),
    ROLE_VIEWER: frozenset(
        {SALES_VIEW_ALL, INVENTORY_VIEW, REPORTS_VIEW, COSTS_VIEW}
    ),
}

# Accounts a manager may create, edit, reset or disable.
MANAGER_MANAGEABLE_ROLES = (ROLE_CASHIER, ROLE_VIEWER)


def permissions_for(user):
    if user is None or not user.is_active:
        return frozenset()
    granted = set(ROLE_PERMISSIONS.get(user.role, frozenset()))
    if user.role == ROLE_CASHIER:
        from .models import Setting

        if Setting.get("cashiers_see_costs") == "true":
            granted.add(COSTS_VIEW)
    return frozenset(granted)


def has_permission(user, permission):
    return permission in permissions_for(user)


def can_manage_user(actor, target_role):
    """Whether actor may create or change an account holding target_role."""
    if actor.role == ROLE_ADMIN:
        return True
    if actor.role == ROLE_MANAGER:
        return target_role in MANAGER_MANAGEABLE_ROLES
    return False
