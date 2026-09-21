from flask import Blueprint, jsonify

from ..services import scan_pairing
from ..utils.auth import auth_required, current_user
from ..utils.errors import ApiError, NotFound
from ..utils.validation import get_int, get_str, payload

bp = Blueprint("scan", __name__, url_prefix="/api/scan-sessions")


@bp.post("")
@auth_required
def create_session():
    session = scan_pairing.create_session(current_user().id)
    return jsonify(session), 201


@bp.get("/<code>/poll")
@auth_required
def poll_session(code):
    from flask import request

    after_id = get_int({"after": request.args.get("after")}, "after", default=0, minimum=0)
    entries = scan_pairing.poll(code, after_id, current_user().id)
    if entries is None:
        raise NotFound("That pairing session has expired. Pair the phone again.")
    return jsonify({"items": entries})


@bp.delete("/<code>")
@auth_required
def end_session(code):
    scan_pairing.close_session(code, current_user().id)
    return jsonify({"message": "Session closed."})


@bp.post("/<code>/scan")
def submit_scan(code):
    data = payload()
    barcode = get_str(data, "barcode", required=True, max_length=64)
    entry = scan_pairing.push_scan(code, barcode)
    if entry is None:
        raise ApiError(
            "This pairing code is no longer valid. Ask the till to show a new one.",
            status_code=410,
        )
    return jsonify({"received": True})
