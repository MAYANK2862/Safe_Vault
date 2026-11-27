"""Flask web application and REST API for SafeVault."""

from __future__ import annotations

import os
from pathlib import Path
from flask import Flask, jsonify, render_template, request

from backup_manager import (
    DEFAULT_BACKUP_DIR,
    DEFAULT_DB_PATH,
    DEFAULT_MAX_BACKUPS,
    add_student,
    check_db_health,
    create_backup,
    get_student_count,
    init_db,
    list_backups,
    list_students,
    restore_backup,
    simulate_data_loss,
    utc_now_iso,
)


def create_app(test_config: dict | None = None) -> Flask:
    """Create and configure the SafeVault Flask application."""
    app = Flask(__name__)

    app.config.update(
        DB_PATH=os.environ.get("DB_PATH", DEFAULT_DB_PATH),
        BACKUP_DIR=os.environ.get("BACKUP_DIR", DEFAULT_BACKUP_DIR),
        MAX_BACKUPS=int(os.environ.get("MAX_BACKUPS", str(DEFAULT_MAX_BACKUPS))),
        BACKUP_INTERVAL_SECONDS=int(os.environ.get("BACKUP_INTERVAL_SECONDS", "60")),
    )
    if test_config:
        app.config.update(test_config)

    init_db(app.config["DB_PATH"])
    Path(app.config["BACKUP_DIR"]).mkdir(parents=True, exist_ok=True)

    def _build_dashboard_payload() -> dict:
        db_path = app.config["DB_PATH"]
        backup_dir = app.config["BACKUP_DIR"]
        students = list_students(db_path)
        backups = list_backups(backup_dir)
        db_healthy, db_status = check_db_health(db_path)
        latest_backup = backups[0] if backups else None

        return {
            "student_count": len(students),
            "students": students,
            "backup_count": len(backups),
            "max_backups": app.config["MAX_BACKUPS"],
            "backups": backups,
            "latest_backup": latest_backup,
            "worker_interval_seconds": app.config["BACKUP_INTERVAL_SECONDS"],
            "health": {
                "status": "healthy" if db_healthy else "degraded",
                "database": db_status,
            },
            "server_time": utc_now_iso(),
        }

    @app.get("/")
    def index():
        dashboard = _build_dashboard_payload()
        return render_template("index.html", initial_data=dashboard)

    @app.get("/health")
    def health():
        db_ok, db_msg = check_db_health(app.config["DB_PATH"])
        backup_dir = Path(app.config["BACKUP_DIR"])
        backup_dir_ok = backup_dir.exists() and os.access(backup_dir, os.W_OK)

        healthy = db_ok and backup_dir_ok
        status_code = 200 if healthy else 503
        return (
            jsonify(
                {
                    "status": "healthy" if healthy else "unhealthy",
                    "database": db_msg,
                    "backup_dir_writable": backup_dir_ok,
                    "timestamp": utc_now_iso(),
                }
            ),
            status_code,
        )

    @app.get("/api/dashboard")
    def api_dashboard():
        return jsonify(_build_dashboard_payload()), 200

    @app.get("/api/students")
    def api_list_students():
        db_path = app.config["DB_PATH"]
        students = list_students(db_path)
        return jsonify({"count": len(students), "students": students}), 200

    @app.post("/api/students")
    def api_add_student():
        payload = request.get_json(silent=True) or request.form.to_dict()
        name = payload.get("name", "")
        email = payload.get("email", "")
        course = payload.get("course", "")

        try:
            student = add_student(app.config["DB_PATH"], name=name, email=email, course=course)
            total = get_student_count(app.config["DB_PATH"])
            return (
                jsonify(
                    {
                        "message": f"Student '{student['name']}' added successfully.",
                        "student": student,
                        "student_count": total,
                    }
                ),
                201,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": f"Unable to add student: {exc}"}), 500

    @app.get("/api/backups")
    def api_list_backups():
        backups = list_backups(app.config["BACKUP_DIR"])
        return (
            jsonify(
                {
                    "count": len(backups),
                    "max_backups": app.config["MAX_BACKUPS"],
                    "backups": backups,
                }
            ),
            200,
        )

    @app.post("/api/backups")
    def api_create_backup():
        try:
            backup = create_backup(
                db_path=app.config["DB_PATH"],
                backup_dir=app.config["BACKUP_DIR"],
                max_backups=app.config["MAX_BACKUPS"],
            )
            return (
                jsonify(
                    {
                        "message": f"Backup '{backup['filename']}' created and verified.",
                        "backup": backup,
                    }
                ),
                201,
            )
        except Exception as exc:
            return jsonify({"error": f"Backup failed: {exc}"}), 500

    @app.post("/api/backups/restore")
    def api_restore_backup():
        payload = request.get_json(silent=True) or {}
        filename = payload.get("filename")
        try:
            result = restore_backup(
                db_path=app.config["DB_PATH"],
                backup_dir=app.config["BACKUP_DIR"],
                filename=filename,
            )
            return (
                jsonify(
                    {
                        "message": (
                            f"Restored {result['restored_student_count']} student record(s) "
                            f"from '{result['restored_from']}'."
                        ),
                        "restore": result,
                    }
                ),
                200,
            )
        except FileNotFoundError as exc:
            return jsonify({"error": str(exc)}), 404
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": f"Restore failed: {exc}"}), 500

    @app.post("/api/simulate-loss")
    def api_simulate_loss():
        try:
            deleted_count = simulate_data_loss(app.config["DB_PATH"])
            return (
                jsonify(
                    {
                        "message": (
                            f"Simulated data loss complete: deleted {deleted_count} "
                            "student record(s) from the active database."
                        ),
                        "deleted_count": deleted_count,
                    }
                ),
                200,
            )
        except Exception as exc:
            return jsonify({"error": f"Data loss simulation failed: {exc}"}), 500

    @app.errorhandler(404)
    def not_found(_err):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Endpoint not found."}), 404
        return render_template("index.html", initial_data=_build_dashboard_payload()), 404

    @app.errorhandler(500)
    def internal_error(_err):
        if request.path.startswith("/api/"):
            return jsonify({"error": "An unexpected server error occurred."}), 500
        return "Internal Server Error", 500

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
