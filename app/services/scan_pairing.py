"""
Pairing between the POS screen (Mac) and a phone acting as a remote scanner.

A cashier opens "Pair phone" on the till, which mints a short code. The phone
opens /scan/<code> - no login - and every barcode it reads is POSTed here and
queued. The till polls for new items on its own code and adds them to the cart,
exactly as if it had scanned them itself.

Kept in a process-local dict: one Flask worker is normal for a single till in
this MVP. Move to Redis if this runs behind multiple workers/instances.
"""
import secrets
import threading
import time

# Sliding: every scan or poll pushes expiry out again, so a phone stays paired
# for the whole shift and only lapses after this long idle.
SESSION_TTL_SECONDS = 12 * 60 * 60
MAX_QUEUE = 50

_lock = threading.Lock()
_sessions: dict[str, dict] = {}


def _purge_expired():
    now = time.time()
    expired = [code for code, session in _sessions.items() if session["expires_at"] < now]
    for code in expired:
        _sessions.pop(code, None)


def create_session(user_id: int) -> dict:
    with _lock:
        _purge_expired()
        code = secrets.token_hex(3).upper()  # e.g. "A1B2C3"
        while code in _sessions:
            code = secrets.token_hex(3).upper()
        expires_at = time.time() + SESSION_TTL_SECONDS
        _sessions[code] = {
            "user_id": user_id,
            "expires_at": expires_at,
            "queue": [],
            "next_id": 1,
        }
        return {"code": code, "expires_at": expires_at}


def get_session(code: str):
    with _lock:
        _purge_expired()
        return _sessions.get(code.upper())


def push_scan(code: str, barcode: str):
    with _lock:
        _purge_expired()
        session = _sessions.get(code.upper())
        if session is None:
            return None
        entry = {"id": session["next_id"], "barcode": barcode, "at": time.time()}
        session["next_id"] += 1
        session["queue"].append(entry)
        session["queue"] = session["queue"][-MAX_QUEUE:]
        session["expires_at"] = time.time() + SESSION_TTL_SECONDS
        return entry


def poll(code: str, after_id: int, owner_user_id: int):
    with _lock:
        _purge_expired()
        session = _sessions.get(code.upper())
        if session is None or session["user_id"] != owner_user_id:
            return None
        session["expires_at"] = time.time() + SESSION_TTL_SECONDS
        return [entry for entry in session["queue"] if entry["id"] > after_id]


def close_session(code: str, owner_user_id: int) -> bool:
    with _lock:
        session = _sessions.get(code.upper())
        if session is None or session["user_id"] != owner_user_id:
            return False
        _sessions.pop(code.upper(), None)
        return True
