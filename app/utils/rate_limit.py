"""
Small in-process failure counters for sign-in and phone pairing.

The POS runs as one process (see run.py), so a dict is enough and survives
without Redis. Counters reset when the server restarts, which only ever makes
the limit more lenient, never stricter.
"""
import threading
import time
from collections import defaultdict

from .errors import ApiError


class FailureLimiter:
    def __init__(self):
        self._lock = threading.Lock()
        self._hits = defaultdict(list)

    def _recent(self, key, window):
        now = time.time()
        hits = [t for t in self._hits.get(key, []) if now - t < window]
        if hits:
            self._hits[key] = hits
        else:
            self._hits.pop(key, None)
        return hits

    def check(self, key, limit, window, message):
        with self._lock:
            if len(self._recent(key, window)) >= limit:
                raise ApiError(message, status_code=429)

    def record(self, key):
        with self._lock:
            self._hits[key].append(time.time())

    def reset(self, key):
        with self._lock:
            self._hits.pop(key, None)


limiter = FailureLimiter()
