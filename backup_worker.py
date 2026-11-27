"""Automated scheduled backup worker for SafeVault."""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading

from backup_manager import (
    DEFAULT_BACKUP_DIR,
    DEFAULT_DB_PATH,
    DEFAULT_MAX_BACKUPS,
    create_backup,
    init_db,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SafeVault Worker] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("safevault.worker")


def run_backup_cycle(
    db_path: str = DEFAULT_DB_PATH,
    backup_dir: str = DEFAULT_BACKUP_DIR,
    max_backups: int = DEFAULT_MAX_BACKUPS,
) -> dict | None:
    """Execute one backup and verification cycle, logging any errors safely."""
    try:
        init_db(db_path)
        result = create_backup(
            db_path=db_path,
            backup_dir=backup_dir,
            max_backups=max_backups,
        )
        pruned_note = (
            f", pruned={len(result['pruned_backups'])}"
            if result.get("pruned_backups")
            else ""
        )
        logger.info(
            "Backup created: %s (%d bytes, sha256=%s..., status=%s%s)",
            result["filename"],
            result["size_bytes"],
            result["sha256"][:12],
            result["status"],
            pruned_note,
        )
        return result
    except Exception as exc:
        logger.error("Automatic backup cycle failed: %s", exc)
        return None


def main() -> int:
    """Run the automated backup loop until a termination signal is received."""
    db_path = os.environ.get("DB_PATH", DEFAULT_DB_PATH)
    backup_dir = os.environ.get("BACKUP_DIR", DEFAULT_BACKUP_DIR)
    max_backups = int(os.environ.get("MAX_BACKUPS", str(DEFAULT_MAX_BACKUPS)))
    interval_seconds = max(5, int(os.environ.get("BACKUP_INTERVAL_SECONDS", "60")))

    stop_event = threading.Event()

    def _handle_signal(signum, _frame):
        logger.info("Received signal %s; shutting down backup worker gracefully.", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info(
        "Worker started (db=%s, backup_dir=%s, interval=%ss, max_backups=%s).",
        db_path,
        backup_dir,
        interval_seconds,
        max_backups,
    )

    while not stop_event.is_set():
        run_backup_cycle(db_path=db_path, backup_dir=backup_dir, max_backups=max_backups)
        stop_event.wait(interval_seconds)

    logger.info("Backup worker stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
