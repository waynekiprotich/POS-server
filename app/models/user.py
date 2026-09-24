from datetime import datetime, timezone

import bcrypt

from ..extensions import db

# "admin" is the owner role; the stored value is kept so existing accounts keep working.
ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_CASHIER = "cashier"
ROLE_VIEWER = "viewer"
ROLES = (ROLE_ADMIN, ROLE_MANAGER, ROLE_CASHIER, ROLE_VIEWER)
ROLE_LABELS = {
    ROLE_ADMIN: "Owner / Admin",
    ROLE_MANAGER: "Manager",
    ROLE_CASHIER: "Cashier",
    ROLE_VIEWER: "Viewer",
}
# Roles allowed to sign in with a PIN. Owners always use their password.
PIN_ROLES = (ROLE_MANAGER, ROLE_CASHIER)


def utcnow():
    return datetime.now(timezone.utc)


def _salt():
    from flask import current_app, has_app_context

    rounds = current_app.config.get("BCRYPT_ROUNDS", 12) if has_app_context() else 12
    return bcrypt.gensalt(rounds=rounds)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey("businesses.id"), index=True)
    name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    # Optional: small shops often have staff without email addresses.
    email = db.Column(db.String(160), unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    pin_hash = db.Column(db.String(255))
    phone = db.Column(db.String(40))
    role = db.Column(db.String(20), nullable=False, default=ROLE_CASHIER)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_login_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    sales = db.relationship(
        "Sale", back_populates="cashier", lazy="dynamic", foreign_keys="Sale.cashier_id"
    )

    def set_password(self, raw_password):
        self.password_hash = bcrypt.hashpw(
            raw_password.encode("utf-8"), _salt()
        ).decode("utf-8")

    def check_password(self, raw_password):
        if not self.password_hash:
            return False
        return bcrypt.checkpw(
            raw_password.encode("utf-8"), self.password_hash.encode("utf-8")
        )

    def set_pin(self, raw_pin):
        self.pin_hash = bcrypt.hashpw(raw_pin.encode("utf-8"), _salt()).decode(
            "utf-8"
        )

    def check_pin(self, raw_pin):
        if not self.pin_hash:
            return False
        return bcrypt.checkpw(raw_pin.encode("utf-8"), self.pin_hash.encode("utf-8"))

    @property
    def is_admin(self):
        return self.role == ROLE_ADMIN

    @property
    def can_use_pin(self):
        return bool(self.pin_hash) and self.role in PIN_ROLES

    def to_dict(self):
        from ..permissions import permissions_for

        return {
            "id": self.id,
            "name": self.name,
            "username": self.username,
            "email": self.email or None,
            "phone": self.phone,
            "role": self.role,
            "role_label": ROLE_LABELS.get(self.role, self.role),
            "is_active": self.is_active,
            "has_pin": bool(self.pin_hash),
            "permissions": sorted(permissions_for(self)),
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
