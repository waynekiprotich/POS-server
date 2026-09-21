from ..extensions import db
from ..utils.money import money_str
from .user import utcnow

PAYMENT_METHODS = ("cash", "mpesa", "card", "other")


class Sale(db.Model):
    __tablename__ = "sales"

    id = db.Column(db.Integer, primary_key=True)
    sale_number = db.Column(db.String(24), unique=True, nullable=False, index=True)
    cashier_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    discount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    tax = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    payment_status = db.Column(db.String(20), nullable=False, default="paid")
    note = db.Column(db.String(255))
    created_at = db.Column(
        db.DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    cashier = db.relationship("User", back_populates="sales")
    items = db.relationship(
        "SaleItem", back_populates="sale", cascade="all, delete-orphan"
    )
    payment = db.relationship(
        "Payment", back_populates="sale", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def cost_total(self):
        return sum((item.cost_price or 0) * item.quantity for item in self.items)

    @property
    def gross_profit(self):
        return self.subtotal - self.cost_total

    def to_dict(self, include_items=False, include_cost=True):
        data = {
            "id": self.id,
            "sale_number": self.sale_number,
            "cashier_id": self.cashier_id,
            "cashier_name": self.cashier.name if self.cashier else None,
            "subtotal": money_str(self.subtotal),
            "discount": money_str(self.discount),
            "tax": money_str(self.tax),
            "total": money_str(self.total),
            "payment_status": self.payment_status,
            "payment_method": self.payment.payment_method if self.payment else None,
            "item_count": sum(item.quantity for item in self.items),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_cost:
            data["gross_profit"] = money_str(self.gross_profit)
        if include_items:
            data["items"] = [i.to_dict(include_cost=include_cost) for i in self.items]
            data["payment"] = self.payment.to_dict() if self.payment else None
        return data


class SaleItem(db.Model):
    __tablename__ = "sale_items"

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"))
    product_name = db.Column(db.String(180), nullable=False)
    product_sku = db.Column(db.String(60))
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    cost_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)

    sale = db.relationship("Sale", back_populates="items")
    product = db.relationship("Product", back_populates="sale_items")

    def to_dict(self, include_cost=True):
        data = {
            "id": self.id,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "product_sku": self.product_sku,
            "quantity": self.quantity,
            "unit_price": money_str(self.unit_price),
            "subtotal": money_str(self.subtotal),
        }
        if include_cost:
            data["cost_price"] = money_str(self.cost_price)
        return data


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=False)
    payment_method = db.Column(db.String(20), nullable=False, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    reference = db.Column(db.String(80))
    received_amount = db.Column(db.Numeric(12, 2))
    change_amount = db.Column(db.Numeric(12, 2))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    sale = db.relationship("Sale", back_populates="payment")

    def to_dict(self):
        return {
            "id": self.id,
            "payment_method": self.payment_method,
            "amount": money_str(self.amount),
            "reference": self.reference,
            "received_amount": money_str(self.received_amount),
            "change_amount": money_str(self.change_amount),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
