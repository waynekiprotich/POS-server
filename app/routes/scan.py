import re

from flask import Blueprint, jsonify, request

from ..permissions import POS_SELL
from ..services import scan_pairing
from ..utils.auth import current_user, permission_required
from ..utils.errors import ApiError, NotFound
from ..utils.rate_limit import limiter
from ..utils.validation import arg_int, get_str, payload

bp = Blueprint("scan", __name__, url_prefix="/api/scan-sessions")

BARCODE_PATTERN = re.compile(r"^[\x21-\x7e]{1,64}$")
EXPIRED = "This pairing has ended. On the till, open Pair phone and scan the new QR code."
# Wrong codes per phone address before it must wait; stops code guessing.
BAD_CODE_LIMIT = 20
BAD_CODE_WINDOW = 10 * 60


def _phone_key():
    return "scan:%s" % (request.remote_addr or "unknown")


def _check_phone():
    limiter.check(
        _phone_key(),
        BAD_CODE_LIMIT,
        BAD_CODE_WINDOW,
        "Too many wrong pairing codes from this phone. Wait a few minutes.",
    )


@bp.post("")
@permission_required(POS_SELL)
def create_session():
    return jsonify(scan_pairing.create_session(current_user().id)), 201


@bp.get("/<code>/poll")
@permission_required(POS_SELL)
def poll_session(code):
    result = scan_pairing.poll(code, arg_int("after", default=0) or 0, current_user().id)
    if result is None:
        raise NotFound(EXPIRED)
    return jsonify(result)


@bp.delete("/<code>")
@permission_required(POS_SELL)
def end_session(code):
    scan_pairing.close_session(code, current_user().id)
    return jsonify({"message": "Phone disconnected."})


@bp.get("/<code>")
def check_session(code):
    """The phone checks its code is live before opening the camera."""
    _check_phone()
    if not scan_pairing.mark_phone_seen(code):
        limiter.record(_phone_key())
        raise ApiError(EXPIRED, status_code=410)
    return jsonify({"paired": True})


@bp.post("/<code>/scan")
def submit_scan(code):
    _check_phone()
    barcode = get_str(payload(), "barcode", required=True, max_length=64)
    if not BARCODE_PATTERN.match(barcode):
        raise ApiError("That barcode could not be read. Try again.", field="barcode")
    entry = scan_pairing.push_scan(code, barcode)
    if entry is None:
        limiter.record(_phone_key())
        raise ApiError(EXPIRED, status_code=410)
    return jsonify({"received": True, "id": entry["id"]})
