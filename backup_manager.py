"""Core database, backup, verification, and restore logic for SafeVault."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import os
from pathlib import Path
import re
import shutil
import sqlite3
import threading
import uuid

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = os.environ.get("DB_PATH", str(BASE_DIR / "data" / "safevault.db"))
DEFAULT_BACKUP_DIR = os.environ.get("BACKUP_DIR", str(BASE_DIR / "backups"))
DEFAULT_MAX_BACKUPS = int(os.environ.get("MAX_BACKUPS", "10"))

BACKUP_PREFIX = "safevault_backup_"
BACKUP_EXT = ".db"
CHECKSUM_EXT = ".sha256"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_FILENAME_RE = re.compile(r"^safevault_backup_(\d{8})_(\d{6})_(\d{6})\.db$")
_DB_LOCK = threading.RLock()


def utc_now_iso() -> str:
    """Return the current UTC timestamp formatted cleanly for display and storage."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _ensure_parent_dir(file_path: str | Path) -> Path:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect_rw(db_path: str | Path) -> sqlite3.Connection:
    path = _ensure_parent_dir(db_path)
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_ro(db_path: str | Path) -> sqlite3.Connection:
    resolved = Path(db_path).resolve()
    conn = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True, timeout=15.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    """Initialize the SQLite database and create the students table if needed."""
    with _DB_LOCK:
        conn = _connect_rw(db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    course TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()


def check_db_health(db_path: str | Path = DEFAULT_DB_PATH) -> tuple[bool, str]:
    """Verify the SQLite database responds to a simple query."""
    try:
        init_db(db_path)
        conn = _connect_rw(db_path)
        try:
            row = conn.execute("SELECT 1 AS ok").fetchone()
            if row and row["ok"] == 1:
                return True, "connected"
            return False, "unexpected query result"
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return False, str(exc)


def list_students(db_path: str | Path = DEFAULT_DB_PATH) -> list[dict]:
    """Return all student records ordered newest first."""
    init_db(db_path)
    with _DB_LOCK:
        conn = _connect_rw(db_path)
        try:
            rows = conn.execute(
                """
                SELECT id, name, email, course, created_at
                FROM students
                ORDER BY id DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()


def get_student_count(db_path: str | Path = DEFAULT_DB_PATH) -> int:
    """Return total number of student records in the database."""
    init_db(db_path)
    with _DB_LOCK:
        conn = _connect_rw(db_path)
        try:
            row = conn.execute("SELECT COUNT(*) AS total FROM students").fetchone()
            return int(row["total"]) if row else 0
        finally:
            conn.close()


def add_student(
    db_path: str | Path,
    name: str,
    email: str,
    course: str,
) -> dict:
    """Validate and insert a new student record using parameterized SQL."""
    clean_name = (name or "").strip()
    clean_email = (email or "").strip().lower()
    clean_course = (course or "").strip()

    if len(clean_name) < 2 or len(clean_name) > 100:
        raise ValueError("Student name must be between 2 and 100 characters.")
    if not clean_email or len(clean_email) > 120 or not _EMAIL_RE.match(clean_email):
        raise ValueError("Please provide a valid email address.")
    if len(clean_course) < 2 or len(clean_course) > 100:
        raise ValueError("Course name must be between 2 and 100 characters.")

    created_at = utc_now_iso()
    init_db(db_path)

    with _DB_LOCK:
        conn = _connect_rw(db_path)
        try:
            cursor = conn.execute(
                """
                INSERT INTO students (name, email, course, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (clean_name, clean_email, clean_course, created_at),
            )
            conn.commit()
            new_id = cursor.lastrowid
            row = conn.execute(
                """
                SELECT id, name, email, course, created_at
                FROM students
                WHERE id = ?
                """,
                (new_id,),
            ).fetchone()
            return dict(row)
        except sqlite3.IntegrityError as exc:
            raise ValueError("A student with this email address already exists.") from exc
        finally:
            conn.close()


def simulate_data_loss(db_path: str | Path = DEFAULT_DB_PATH) -> int:
    """Simulate accidental data loss by deleting all student rows only."""
    init_db(db_path)
    with _DB_LOCK:
        conn = _connect_rw(db_path)
        try:
            row = conn.execute("SELECT COUNT(*) AS total FROM students").fetchone()
            existing_count = int(row["total"]) if row else 0
            conn.execute("DELETE FROM students")
            conn.commit()
            return existing_count
        finally:
            conn.close()


def compute_sha256(file_path: str | Path) -> str:
    """Compute the SHA-256 hex digest for a file in 64 KB chunks."""
    digest = hashlib.sha256()
    with open(file_path, "rb") as handle:
        while chunk := handle.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


def check_sqlite_integrity(db_path: str | Path) -> tuple[bool, str]:
    """Run SQLite PRAGMA integrity_check on a database file."""
    path = Path(db_path)
    if not path.exists() or path.stat().st_size == 0:
        return False, "database file is missing or empty"

    try:
        conn = _connect_ro(path)
        try:
            rows = conn.execute("PRAGMA integrity_check").fetchall()
            messages = [str(row[0]) for row in rows]
            if len(messages) == 1 and messages[0].lower() == "ok":
                return True, "ok"
            return False, "; ".join(messages) or "unknown integrity failure"
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return False, str(exc)


def _checksum_path_for(backup_path: Path) -> Path:
    return Path(f"{backup_path}{CHECKSUM_EXT}")


def _parse_backup_timestamp(backup_path: Path) -> str:
    match = _FILENAME_RE.match(backup_path.name)
    if match:
        date_part, time_part, _ = match.groups()
        parsed = datetime.strptime(f"{date_part}{time_part}", "%Y%m%d%H%M%S")
        return parsed.strftime("%Y-%m-%d %H:%M:%S UTC")

    mtime = datetime.fromtimestamp(backup_path.stat().st_mtime, tz=timezone.utc)
    return mtime.strftime("%Y-%m-%d %H:%M:%S UTC")


def _write_text_atomic(target_path: Path, content: str) -> None:
    tmp_path = target_path.with_name(f".{target_path.name}.{uuid.uuid4().hex}.tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, target_path)


def _remove_file_if_exists(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def prune_old_backups(
    backup_dir: str | Path = DEFAULT_BACKUP_DIR,
    max_backups: int = DEFAULT_MAX_BACKUPS,
) -> list[str]:
    """Keep only the newest `max_backups` backup files and remove older ones."""
    if max_backups < 1:
        raise ValueError("max_backups must be at least 1.")

    dir_path = Path(backup_dir)
    if not dir_path.exists():
        return []

    backup_files = sorted(
        (
            p
            for p in dir_path.iterdir()
            if p.is_file()
            and p.name.startswith(BACKUP_PREFIX)
            and p.name.endswith(BACKUP_EXT)
        ),
        key=lambda p: p.name,
        reverse=True,
    )

    removed: list[str] = []
    for old_backup in backup_files[max_backups:]:
        checksum_file = _checksum_path_for(old_backup)
        _remove_file_if_exists(old_backup)
        _remove_file_if_exists(checksum_file)
        removed.append(old_backup.name)

    return removed


def create_backup(
    db_path: str | Path = DEFAULT_DB_PATH,
    backup_dir: str | Path = DEFAULT_BACKUP_DIR,
    max_backups: int = DEFAULT_MAX_BACKUPS,
) -> dict:
    """Create a consistent SQLite backup, save its SHA-256 checksum, and enforce retention."""
    init_db(db_path)
    backup_root = Path(backup_dir)
    backup_root.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{BACKUP_PREFIX}{timestamp}{BACKUP_EXT}"
    final_backup_path = backup_root / filename
    tmp_backup_path = backup_root / f".{filename}.{uuid.uuid4().hex}.tmp"

    with _DB_LOCK:
        src_conn = _connect_rw(db_path)
        dst_conn = sqlite3.connect(str(tmp_backup_path), timeout=30.0)
        try:
            src_conn.backup(dst_conn)
            dst_conn.commit()
        finally:
            dst_conn.close()
            src_conn.close()

    integrity_ok, integrity_msg = check_sqlite_integrity(tmp_backup_path)
    if not integrity_ok:
        _remove_file_if_exists(tmp_backup_path)
        raise RuntimeError(f"Backup integrity check failed: {integrity_msg}")

    os.replace(tmp_backup_path, final_backup_path)
    sha256_hash = compute_sha256(final_backup_path)
    _write_text_atomic(
        _checksum_path_for(final_backup_path),
        f"{sha256_hash}  {filename}\n",
    )

    pruned = prune_old_backups(backup_root, max_backups=max_backups)
    details = verify_backup(final_backup_path)
    details["pruned_backups"] = pruned
    return details


def verify_backup(backup_path: str | Path) -> dict:
    """Verify SHA-256 checksum and SQLite integrity for a single backup file."""
    path = Path(backup_path)
    checksum_path = _checksum_path_for(path)

    size_bytes = path.stat().st_size if path.exists() else 0
    created_at = _parse_backup_timestamp(path) if path.exists() else "Unknown"
    actual_sha256 = compute_sha256(path) if path.exists() and size_bytes > 0 else ""

    expected_sha256 = ""
    checksum_missing = not checksum_path.exists()
    if not checksum_missing:
        raw_text = checksum_path.read_text(encoding="utf-8").strip()
        if raw_text:
            expected_sha256 = raw_text.split()[0].lower()

    checksum_valid = bool(
        expected_sha256
        and actual_sha256
        and hmac.compare_digest(expected_sha256, actual_sha256)
    )
    integrity_valid, integrity_msg = check_sqlite_integrity(path)

    if not path.exists() or size_bytes == 0:
        status = "Missing or Empty"
    elif checksum_missing or not expected_sha256:
        status = "Missing Checksum"
    elif not checksum_valid:
        status = "Checksum Mismatch"
    elif not integrity_valid:
        status = "Corrupted SQLite"
    else:
        status = "Verified"

    return {
        "filename": path.name,
        "size_bytes": size_bytes,
        "created_at": created_at,
        "sha256": actual_sha256,
        "expected_sha256": expected_sha256,
        "checksum_valid": checksum_valid,
        "integrity_valid": integrity_valid,
        "integrity_message": integrity_msg,
        "valid": checksum_valid and integrity_valid,
        "status": status,
    }


def list_backups(backup_dir: str | Path = DEFAULT_BACKUP_DIR) -> list[dict]:
    """List all backups newest-first along with their live verification status."""
    dir_path = Path(backup_dir)
    if not dir_path.exists():
        return []

    backup_files = sorted(
        (
            p
            for p in dir_path.iterdir()
            if p.is_file()
            and p.name.startswith(BACKUP_PREFIX)
            and p.name.endswith(BACKUP_EXT)
        ),
        key=lambda p: p.name,
        reverse=True,
    )
    return [verify_backup(backup_file) for backup_file in backup_files]


def _select_backup_for_restore(
    backup_dir: Path,
    filename: str | None = None,
) -> dict:
    backups = list_backups(backup_dir)
    if not backups:
        raise FileNotFoundError("No backup files found in the backups directory.")

    if filename:
        for item in backups:
            if item["filename"] == filename:
                if not item["valid"]:
                    raise RuntimeError(
                        f"Selected backup '{filename}' failed verification ({item['status']})."
                    )
                return item
        raise FileNotFoundError(f"Backup '{filename}' was not found.")

    for item in backups:
        if item["valid"]:
            return item

    raise RuntimeError("No valid verified backup found to restore.")


def restore_backup(
    db_path: str | Path = DEFAULT_DB_PATH,
    backup_dir: str | Path = DEFAULT_BACKUP_DIR,
    filename: str | None = None,
) -> dict:
    """Verify and restore the latest valid backup (or a specific verified one) via a temp DB file."""
    backup_root = Path(backup_dir)
    selected = _select_backup_for_restore(backup_root, filename=filename)
    source_backup_path = backup_root / selected["filename"]

    target_db_path = _ensure_parent_dir(db_path)
    temp_restore_path = target_db_path.with_name(
        f"{target_db_path.name}.restore_tmp_{uuid.uuid4().hex}"
    )

    try:
        shutil.copy2(source_backup_path, temp_restore_path)

        # Re-verify checksum and SQLite integrity on the temporary copy before replacing live DB.
        temp_sha256 = compute_sha256(temp_restore_path)
        if not hmac.compare_digest(temp_sha256, selected["expected_sha256"]):
            raise RuntimeError("Temporary restore file failed SHA-256 verification.")

        integrity_ok, integrity_msg = check_sqlite_integrity(temp_restore_path)
        if not integrity_ok:
            raise RuntimeError(f"Temporary restore file failed integrity check: {integrity_msg}")

        with _DB_LOCK:
            for suffix in ("-wal", "-shm", "-journal"):
                _remove_file_if_exists(Path(f"{target_db_path}{suffix}"))
            os.replace(temp_restore_path, target_db_path)
            init_db(target_db_path)
            restored_count = get_student_count(target_db_path)

        return {
            "restored_from": selected["filename"],
            "sha256": selected["sha256"],
            "backup_created_at": selected["created_at"],
            "restored_student_count": restored_count,
            "restored_at": utc_now_iso(),
        }
    finally:
        _remove_file_if_exists(temp_restore_path)
