from ..extensions import db
from ..models import ActivityLog


def log_activity(user, action, entity_type=None, entity_id=None, description=None):
    """Record an audit trail entry inside the caller's transaction."""
    db.session.add(
        ActivityLog(
            user_id=user.id if user else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
        )
    )
