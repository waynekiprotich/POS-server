"""
Pairing between a till and a phone acting as its barcode scanner.

The till opens "Pair phone", which mints a code. The phone opens
/scan/<code> on the shop network (no login, no internet) and every barcode it
reads is POSTed here and queued. The till polls its own code and adds each
barcode to the cart exactly as if it had scanned it itself.

The code is the phone's only credential and it can do exactly one thing: add a
barcode to one till's queue. It never sees prices, the cart or any account.

Sessions live in process memory. The POS runs as a single process (run.py
starts one worker with threads), so every request sees the same dict. A server
restart ends all pairings, and tills simply pair again.
"""
import secrets
import threading
import time

# No 0/O or 1/I/L so the code can be typed from the screen without mistakes.
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 8  # 31^8 ≈ 8.5e11 combinations: not guessable in a shift.

# Sliding: each scan or poll extends the session, so a phone stays paired for
# the whole shift and lapses after this long idle...
IDLE_TTL_SECONDS = 60 * 60
# ...but never lives longer than this, so a forgotten pairing does not linger.
MAX_AGE_SECONDS = 14 * 60 * 60
MAX_QUEUE = 50
MAX_SESSIONS_PER_USER = 5

_lock = threading.Lock()
_sessions: dict[str, dict] = {}


def normalise(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def _new_code():
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def _expires_at(session, now):
    return min(session["last_seen"] + IDLE_TTL_SECONDS, session["created_at"] + MAX_AGE_SECONDS)


def _purge_expired(now=None):
    now = now or time.time()
    expired = [code for code, s in _sessions.items() if _expires_at(s, now) <= now]
    for code in expired:
        _sessions.pop(code, None)


def _public(code, session, now):
    return {
        "code": code,
        "expires_at": _expires_at(session, now),
        "created_at": session["created_at"],
        "scans": session["next_id"] - 1,
        "phone_seen": session["phone_seen"],
    }


def create_session(user_id: int) -> dict:
    with _lock:
        now = time.time()
        _purge_expired(now)
        # A till that keeps re-pairing should not pile up live codes.
        mine = sorted(
            (c for c, s in _sessions.items() if s["user_id"] == user_id),
            key=lambda c: _sessions[c]["created_at"],
        )
        for code in mine[: max(0, len(mine) - MAX_SESSIONS_PER_USER + 1)]:
            _sessions.pop(code, None)

        code = _new_code()
        while code in _sessions:
            code = _new_code()
        _sessions[code] = {
            "user_id": user_id,
            "created_at": now,
            "last_seen": now,
            "queue": [],
            "next_id": 1,
            "phone_seen": False,
        }
        return _public(code, _sessions[code], now)


def exists(code: str) -> bool:
    with _lock:
        _purge_expired()
        return normalise(code) in _sessions


def push_scan(code: str, barcode: str):
    with _lock:
        now = time.time()
        _purge_expired(now)
        session = _sessions.get(normalise(code))
        if session is None:
            return None
        entry = {"id": session["next_id"], "barcode": barcode, "at": now}
        session["next_id"] += 1
        session["queue"] = (session["queue"] + [entry])[-MAX_QUEUE:]
        session["last_seen"] = now
        session["phone_seen"] = True
        return entry


def mark_phone_seen(code: str) -> bool:
    with _lock:
        session = _sessions.get(normalise(code))
        if session is None:
            return False
        session["phone_seen"] = True
        return True


def poll(code: str, after_id: int, owner_user_id: int):
    with _lock:
        now = time.time()
        _purge_expired(now)
        session = _sessions.get(normalise(code))
        if session is None or session["user_id"] != owner_user_id:
            return None
        session["last_seen"] = now
        return {
            "items": [entry for entry in session["queue"] if entry["id"] > after_id],
            "session": _public(normalise(code), session, now),
        }


def close_session(code: str, owner_user_id: int) -> bool:
    with _lock:
        key = normalise(code)
        session = _sessions.get(key)
        if session is None or session["user_id"] != owner_user_id:
            return False
        _sessions.pop(key, None)
        return True


def close_all_for_user(user_id: int):
    with _lock:
        for code in [c for c, s in _sessions.items() if s["user_id"] == user_id]:
            _sessions.pop(code, None)


def reset():
    """Drop every session (tests, and server restart semantics)."""
    with _lock:
        _sessions.clear()
