# SafeVault — Automated Backup & Disaster Recovery System

A web dashboard that stores student records in SQLite, automatically backs up the database, verifies backups using SHA-256 and SQLite integrity checks, and restores records after simulated data loss.

---

## Tech Stack

- **Python 3.11 + Flask** — Web server & REST API
- **SQLite** — Database
- **Docker + Docker Compose** — Containerization
- **HTML / CSS / JavaScript** — Dashboard UI

---

## Project Structure

```
Safe_Vault/
├── app.py               # Flask web server & API
├── backup_manager.py    # Backup, verify, and restore logic
├── backup_worker.py     # Automated 60-second backup worker
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── templates/index.html # Dashboard UI
├── static/style.css
├── static/app.js
├── backups/             # Backup files stored here
└── tests/
    └── test_safevault.py
```

---

## How to Run

> Make sure Docker Desktop is running first.

```powershell
# 1. Go to project folder
cd "C:\Users\mayank jha\Desktop\Safe_Vault"

# 2. Build and start
docker compose up --build -d

# 3. Open in browser
# http://localhost:8082
```

---

## Features

- Add and view student records
- Create manual backups
- Automatic backup every 60 seconds (background worker)
- SHA-256 checksum verification for every backup
- SQLite PRAGMA integrity check
- Restore from latest valid backup
- Simulate data loss (deletes student rows only)
- Backup history with timestamps, file size, and status
- Keeps latest 10 backups automatically
- Health check at `/health`

---

## Run Tests

```powershell
docker compose run --rm --no-deps web python -m unittest discover -s tests -v
```

---

## CI/CD Pipeline

This project uses **GitHub Actions** for automated testing and Docker build verification.

**Triggered on every push to `main`:**

1. **Run Tests** — Sets up Python 3.11, installs dependencies, and runs all 7 automated tests
2. **Docker Build Check** — Builds the Docker image to verify no build errors (runs only if tests pass)

View pipeline results: [GitHub Actions](https://github.com/MAYANK2862/Safe_Vault/actions)

---

## Stop

```powershell
docker compose down
```
