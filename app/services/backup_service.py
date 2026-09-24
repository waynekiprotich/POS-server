"""
Local database backups.

SQLite's online backup API copies a consistent snapshot even while tills are
selling, unlike copying pos.db (and its -wal file) directly. Backups are
plain SQLite files that open with any SQLite tool.
"""
import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone

from flask import current_app

from ..extensions import db
from ..utils.errors import ApiError

NAME_PATTERN = re.compile(r"^pos-(\d{8}-\d{6})(?:-(auto|manual|pre-restore))?\.db$")
AUTO_INTERVAL_SECONDS = 24 * 60 * 60
CHECK_EVERY_SECONDS = 30 * 60

_write_lock = threading.Lock()
_scheduler_started = False


def backup_dir():
    path = current_app.config["BACKUP_DIR"]
    os.makedirs(path, exist_ok=True)
    return path


def sqlite_path():
    url = db.engine.url
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    return url.database


def is_supported():
    return sqlite_path() is not None


def _require_supported():
    if not is_supported():
        raise ApiError(
            "Built-in backups work with the local SQLite database. For PostgreSQL use "
            "pg_dump or your provider's backups.",
            status_code=400,
        )


def _describe(name):
    path = os.path.join(backup_dir(), name)
    stat = os.stat(path)
    match = NAME_PATTERN.match(name)
    return {
        "name": name,
        "size": stat.st_size,
        "kind": (match.group(2) if match and match.group(2) else "manual"),
        "created_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def list_backups():
    if not is_supported():
        return []
    names = [n for n in os.listdir(backup_dir()) if NAME_PATTERN.match(n)]
    names.sort(reverse=True)
    return [_describe(name) for name in names]


def resolve(name):
    """Full path of an existing backup; rejects anything that is not one."""
    if not NAME_PATTERN.match(name or ""):
        raise ApiError("That backup could not be found.", status_code=404)
    path = os.path.join(backup_dir(), name)
    if not os.path.isfile(path):
        raise ApiError("That backup could not be found.", status_code=404)
    return path


def copy_database(source_path, target_path):
    """Consistent copy of a live SQLite file using the backup API."""
    source = sqlite3.connect("file:%s?mode=ro" % source_path, uri=True, timeout=30)
    try:
        target = sqlite3.connect(target_path)
        try:
            source.backup(target)
            # One self-contained file: no -wal/-shm companions to lose when copying.
            target.execute("PRAGMA journal_mode=DELETE")
            ok = target.execute("PRAGMA integrity_check").fetchone()[0]
            if ok != "ok":
                raise RuntimeError("Backup failed its integrity check: %s" % ok)
        finally:
            target.close()
    finally:
        source.close()


def create_backup(kind="manual"):
    _require_supported()
    with _write_lock:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        name = "pos-%s-%s.db" % (stamp, kind)
        path = os.path.join(backup_dir(), name)
        if os.path.exists(path):
            raise ApiError("A backup was made a moment ago. Try again in a second.")
        temporary = path + ".partial"
        try:
            copy_database(sqlite_path(), temporary)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
        os.chmod(path, 0o600)
    prune()
    return _describe(os.path.basename(path))


def prune():
    """Keep the newest N automatic backups; manual ones are never deleted."""
    from ..models import Setting

    try:
        keep = max(1, int(Setting.get("backup_retention") or 14))
    except ValueError:
        keep = 14
    autos = [b["name"] for b in list_backups() if b["kind"] == "auto"]
    for name in autos[keep:]:
        try:
            os.remove(os.path.join(backup_dir(), name))
        except OSError:
            pass


def last_backup_age_seconds():
    backups = list_backups()
    if not backups:
        return None
    newest = max(os.path.getmtime(os.path.join(backup_dir(), b["name"])) for b in backups)
    return time.time() - newest


def run_auto_backup_if_due():
    from ..models import Setting

    if not is_supported() or Setting.get("auto_backup_enabled") != "true":
        return None
    age = last_backup_age_seconds()
    if age is not None and age < AUTO_INTERVAL_SECONDS:
        return None
    return create_backup("auto")


def start_scheduler(app):
    """Daily automatic backup, checked every half hour while the POS runs."""
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    def loop():
        while True:
            try:
                with app.app_context():
                    made = run_auto_backup_if_due()
                    if made:
                        app.logger.info("Automatic backup created: %s", made["name"])
            except Exception:  # never let a failed backup stop the till
                app.logger.exception("Automatic backup failed")
            time.sleep(CHECK_EVERY_SECONDS)

    thread = threading.Thread(target=loop, name="pos-auto-backup", daemon=True)
    thread.start()
