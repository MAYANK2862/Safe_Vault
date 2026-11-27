"""Automated tests for SafeVault backup, verification, and disaster recovery."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

from app import create_app
from backup_manager import (
    add_student,
    compute_sha256,
    create_backup,
    get_student_count,
    list_backups,
    verify_backup,
)
from backup_worker import run_backup_cycle


class SafeVaultTestCase(unittest.TestCase):
    """End-to-end tests covering CRUD, backups, verification, and recovery."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "data" / "safevault_test.db"
        self.backup_dir = self.root / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self.app = create_app(
            {
                "TESTING": True,
                "DB_PATH": str(self.db_path),
                "BACKUP_DIR": str(self.backup_dir),
                "MAX_BACKUPS": 10,
                "BACKUP_INTERVAL_SECONDS": 60,
            }
        )
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_health_endpoint(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["database"], "connected")
        self.assertTrue(data["backup_dir_writable"])

    def test_add_and_list_student_records(self) -> None:
        res1 = self.client.post(
            "/api/students",
            json={
                "name": "Aarav Sharma",
                "email": "aarav@college.edu",
                "course": "B.Tech Computer Science",
            },
        )
        self.assertEqual(res1.status_code, 201)
        self.assertEqual(res1.get_json()["student_count"], 1)

        res2 = self.client.post(
            "/api/students",
            json={
                "name": "Priya Verma",
                "email": "priya@college.edu",
                "course": "B.Sc Data Science",
            },
        )
        self.assertEqual(res2.status_code, 201)
        self.assertEqual(res2.get_json()["student_count"], 2)

        list_res = self.client.get("/api/students")
        self.assertEqual(list_res.status_code, 200)
        payload = list_res.get_json()
        self.assertEqual(payload["count"], 2)
        names = {s["name"] for s in payload["students"]}
        self.assertEqual(names, {"Aarav Sharma", "Priya Verma"})

        # Invalid email and duplicate email should return 400
        bad_email = self.client.post(
            "/api/students",
            json={"name": "Bad User", "email": "not-an-email", "course": "BCA"},
        )
        self.assertEqual(bad_email.status_code, 400)

        dup_email = self.client.post(
            "/api/students",
            json={
                "name": "Duplicate",
                "email": "aarav@college.edu",
                "course": "BCA",
            },
        )
        self.assertEqual(dup_email.status_code, 400)

    def test_create_backup_checksum_and_integrity(self) -> None:
        add_student(self.db_path, "Rohan Mehta", "rohan@college.edu", "MCA")

        res = self.client.post("/api/backups")
        self.assertEqual(res.status_code, 201)
        backup = res.get_json()["backup"]

        backup_file = self.backup_dir / backup["filename"]
        checksum_file = self.backup_dir / f"{backup['filename']}.sha256"
        self.assertTrue(backup_file.exists())
        self.assertTrue(checksum_file.exists())
        self.assertTrue(backup["checksum_valid"])
        self.assertTrue(backup["integrity_valid"])
        self.assertTrue(backup["valid"])
        self.assertEqual(backup["status"], "Verified")

    def test_tampered_and_corrupted_backup_detection(self) -> None:
        add_student(self.db_path, "Neha Gupta", "neha@college.edu", "B.Tech IT")
        backup = create_backup(self.db_path, self.backup_dir)
        backup_file = self.backup_dir / backup["filename"]

        # Tamper with checksum file to simulate file modification
        checksum_file = Path(f"{backup_file}.sha256")
        checksum_file.write_text("0" * 64 + f"  {backup['filename']}\n", encoding="utf-8")
        tampered = verify_backup(backup_file)
        self.assertFalse(tampered["checksum_valid"])
        self.assertFalse(tampered["valid"])
        self.assertEqual(tampered["status"], "Checksum Mismatch")

        # Overwrite backup with garbage bytes + matching checksum to test PRAGMA integrity_check
        backup_file.write_bytes(b"corrupted-not-a-sqlite-file")
        new_hash = compute_sha256(backup_file)
        checksum_file.write_text(f"{new_hash}  {backup['filename']}\n", encoding="utf-8")
        corrupted = verify_backup(backup_file)
        self.assertTrue(corrupted["checksum_valid"])
        self.assertFalse(corrupted["integrity_valid"])
        self.assertFalse(corrupted["valid"])
        self.assertEqual(corrupted["status"], "Corrupted SQLite")

    def test_simulate_data_loss_and_restore_latest_valid_backup(self) -> None:
        add_student(self.db_path, "Kabir Nair", "kabir@college.edu", "B.Tech AI")
        add_student(self.db_path, "Ananya Iyer", "ananya@college.edu", "B.Tech CSE")

        valid_backup = create_backup(self.db_path, self.backup_dir)
        time.sleep(0.02)

        # Create a newer backup and corrupt it so restore must skip it and pick the valid one
        newer_backup = create_backup(self.db_path, self.backup_dir)
        newer_path = self.backup_dir / newer_backup["filename"]
        newer_path.write_bytes(b"corrupted-snapshot")

        loss_res = self.client.post("/api/simulate-loss")
        self.assertEqual(loss_res.status_code, 200)
        self.assertEqual(loss_res.get_json()["deleted_count"], 2)
        self.assertEqual(get_student_count(self.db_path), 0)

        # Table schema should still exist after simulated data loss
        conn = sqlite3.connect(self.db_path)
        try:
            table_row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='students'"
            ).fetchone()
            self.assertIsNotNone(table_row)
        finally:
            conn.close()

        restore_res = self.client.post("/api/backups/restore", json={})
        self.assertEqual(restore_res.status_code, 200)
        restore_data = restore_res.get_json()["restore"]
        self.assertEqual(restore_data["restored_from"], valid_backup["filename"])
        self.assertEqual(restore_data["restored_student_count"], 2)
        self.assertEqual(get_student_count(self.db_path), 2)

    def test_retention_keeps_latest_10_backups(self) -> None:
        add_student(self.db_path, "Vikram Rao", "vikram@college.edu", "BCA")
        created_names = []
        for _ in range(12):
            info = create_backup(self.db_path, self.backup_dir, max_backups=10)
            created_names.append(info["filename"])
            time.sleep(0.005)

        remaining = list_backups(self.backup_dir)
        self.assertEqual(len(remaining), 10)
        remaining_names = {b["filename"] for b in remaining}
        self.assertNotIn(created_names[0], remaining_names)
        self.assertNotIn(created_names[1], remaining_names)
        self.assertIn(created_names[-1], remaining_names)

        # Verify orphaned .sha256 files were also removed
        sha_files = list(self.backup_dir.glob("*.sha256"))
        self.assertEqual(len(sha_files), 10)

    def test_worker_backup_cycle(self) -> None:
        add_student(self.db_path, "Meera Joshi", "meera@college.edu", "M.Tech")
        result = run_backup_cycle(
            db_path=str(self.db_path),
            backup_dir=str(self.backup_dir),
            max_backups=10,
        )
        self.assertIsNotNone(result)
        self.assertTrue(result["valid"])


if __name__ == "__main__":
    unittest.main()
