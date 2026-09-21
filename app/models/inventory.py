from ..extensions import db
from .user import utcnow

MOVEMENT_SALE = "SALE"
MOVEMENT_RESTOCK = "RESTOCK"
MOVEMENT_ADJUSTMENT = "ADJUSTMENT"
MOVEMENT_RETURN = "RETURN"
MOVEMENT_DAMAGED = "DAMAGED"
MOVEMENT_EXPIRED = "EXPIRED"
MOVEMENT_TYPES = (
    MOVEMENT_SALE,
    MOVEMENT_RESTOCK,
    MOVEMENT_ADJUSTMENT,
    MOVEMENT_RETURN,
    MOVEMENT_DAMAGED,
    MOVEMENT_EXPIRED,
)


class InventoryMovement(db.Model):
    __tablename__ = "inventory_movements"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    movement_type = db.Column(db.String(20), nullable=False, index=True)
    quantity_change = db.Column(db.Integer, nullable=False)
    previous_quantity = db.Column(db.Integer, nullable=False)
    new_quantity = db.Column(db.Integer, nullable=False)
    reference = db.Column(db.String(80))
    note = db.Column(db.String(255))
    created_at = db.Column(
        db.DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    product = db.relationship("Product", back_populates="movements")
    user = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "product_name": self.product.name if self.product else None,
            "user_id": self.user_id,
            "user_name": self.user.name if self.user else None,
            "movement_type": self.movement_type,
            "quantity_change": self.quantity_change,
            "previous_quantity": self.previous_quantity,
            "new_quantity": self.new_quantity,
            "reference": self.reference,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
