from ..extensions import db
from .user import utcnow


class Business(db.Model):
    """The shop this installation serves.

    One row per installation today. Other tables carry a nullable business_id
    so a later multi-business version can scope data without a rewrite.
    Editable details (name, address, currency...) live in settings; this row
    records identity and whether first-run setup has finished.
    """

    __tablename__ = "businesses"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    setup_completed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    @staticmethod
    def current():
        return Business.query.order_by(Business.id.asc()).first()

    @staticmethod
    def current_id():
        business = Business.current()
        return business.id if business else None

    @staticmethod
    def setup_completed():
        business = Business.current()
        return bool(business and business.setup_completed_at)
