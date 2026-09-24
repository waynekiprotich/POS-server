from ..extensions import db
from ..utils.money import money_str
from .user import utcnow

STOCK_IN = "in_stock"
STOCK_LOW = "low_stock"
STOCK_OUT = "out_of_stock"


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey("businesses.id"), index=True)
    name = db.Column(db.String(180), nullable=False, index=True)
    description = db.Column(db.Text)
    sku = db.Column(db.String(60), unique=True, nullable=False, index=True)
    barcode = db.Column(db.String(64), unique=True, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    cost_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    selling_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    stock_quantity = db.Column(db.Integer, nullable=False, default=0)
    low_stock_threshold = db.Column(db.Integer, nullable=False, default=5)
    unit = db.Column(db.String(20), nullable=False, default="pc")
    brand = db.Column(db.String(120))
    supplier = db.Column(db.String(120))
    image_url = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    category = db.relationship("Category", back_populates="products")
    sale_items = db.relationship("SaleItem", back_populates="product", lazy="dynamic")
    movements = db.relationship(
        "InventoryMovement", back_populates="product", lazy="dynamic"
    )

    @property
    def stock_status(self):
        if self.stock_quantity <= 0:
            return STOCK_OUT
        if self.stock_quantity <= self.low_stock_threshold:
            return STOCK_LOW
        return STOCK_IN

    @property
    def margin(self):
        return (self.selling_price or 0) - (self.cost_price or 0)

    def to_dict(self, include_cost=True):
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "sku": self.sku,
            "barcode": self.barcode,
            "category_id": self.category_id,
            "category_name": self.category.name if self.category else None,
            "selling_price": money_str(self.selling_price),
            "stock_quantity": self.stock_quantity,
            "low_stock_threshold": self.low_stock_threshold,
            "stock_status": self.stock_status,
            "unit": self.unit,
            "brand": self.brand,
            "supplier": self.supplier,
            "image_url": self.image_url,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_cost:
            data["cost_price"] = money_str(self.cost_price)
            data["margin"] = money_str(self.margin)
        return data
