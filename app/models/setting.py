from ..extensions import db
from .user import utcnow

DEFAULT_SETTINGS = {
    "business_name": "POS System",
    "business_address": "",
    "business_phone": "",
    "business_email": "",
    "currency": "KES",
    "currency_symbol": "KSh",
    "receipt_footer": "Thank you",
    "default_low_stock_threshold": "5",
    "tax_enabled": "false",
    "tax_rate": "0",
    "allow_negative_stock": "false",
    "business_tax_pin": "",
    "timezone": "Africa/Nairobi",
    # 58mm / 80mm thermal roll, or a normal A4/Letter printer.
    "receipt_width": "80mm",
    "receipt_show_cashier": "true",
    "pin_login_enabled": "true",
    "cashiers_see_costs": "false",
    # Sign a till out after this many idle minutes (0 = never).
    "idle_logout_minutes": "0",
    "auto_backup_enabled": "true",
    "backup_retention": "14",
}

RECEIPT_WIDTHS = ("58mm", "80mm", "a4")


class Setting(db.Model):
    __tablename__ = "settings"

    key = db.Column(db.String(60), primary_key=True)
    value = db.Column(db.String(500))
    updated_at = db.Column(
        db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    @staticmethod
    def as_dict():
        stored = {s.key: s.value for s in Setting.query.all()}
        merged = dict(DEFAULT_SETTINGS)
        try:
            from flask import current_app

            merged["timezone"] = current_app.config.get("BUSINESS_TIMEZONE") or merged["timezone"]
        except RuntimeError:
            pass
        merged.update({k: v for k, v in stored.items() if v is not None})
        return merged

    @staticmethod
    def get(key, default=None):
        return Setting.as_dict().get(key, default)

    @staticmethod
    def set_many(values):
        for key, value in values.items():
            if key not in DEFAULT_SETTINGS:
                continue
            row = db.session.get(Setting, key)
            if row is None:
                row = Setting(key=key)
                db.session.add(row)
            row.value = "" if value is None else str(value)
