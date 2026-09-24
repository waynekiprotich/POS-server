from flask import Blueprint, jsonify, send_file

from ..permissions import BACKUPS_MANAGE
from ..services import backup_service
from ..utils.activity import log_activity
from ..utils.auth import current_user, permission_required
from ..extensions import db

bp = Blueprint("backups", __name__, url_prefix="/api/backups")


@bp.get("")
@permission_required(BACKUPS_MANAGE)
def list_backups():
    return jsonify(
        {
            "supported": backup_service.is_supported(),
            "directory": backup_service.backup_dir() if backup_service.is_supported() else None,
            "items": backup_service.list_backups(),
        }
    )


@bp.post("")
@permission_required(BACKUPS_MANAGE)
def create_backup():
    backup = backup_service.create_backup("manual")
    log_activity(current_user(), "backup.created", "backup", None, backup["name"])
    db.session.commit()
    return jsonify({"backup": backup}), 201


@bp.get("/<name>/download")
@permission_required(BACKUPS_MANAGE)
def download_backup(name):
    path = backup_service.resolve(name)
    log_activity(current_user(), "backup.downloaded", "backup", None, name)
    db.session.commit()
    return send_file(
        path, as_attachment=True, download_name=name, mimetype="application/octet-stream"
    )
