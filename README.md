# SafeVault — Automated Backup & Disaster Recovery System

SafeVault is a college-level full-stack DevOps & Python project that demonstrates how a web application protects its database against accidental data loss using **automated scheduled backups**, **cryptographic SHA-256 verification**, **SQLite integrity checks**, and **safe temporary-file disaster recovery** inside Docker containers.

---

## 1. Project Overview

- **Live Student Database:** A Flask web dashboard (`http://localhost:8082`) stores student records (`name`, `email`, `course`) in a persistent SQLite database.
- **Automated Backup Worker:** A separate Docker container runs continuously in the background and creates a verified database snapshot every **60 seconds**.
- **Integrity Verification:** Every backup is saved with a unique timestamped filename and verified using both a **SHA-256 checksum** (`.sha256` sidecar file) and SQLite's built-in `PRAGMA integrity_check`.
- **Safe Recovery:** Before restoring, SafeVault checks the backup's checksum and SQLite integrity, copies it to a temporary database file, re-verifies it, and atomically swaps it into place.
- **Retention Policy:** Automatically keeps the **latest 10 backups** so disk space never grows unbounded.

---

## 2. System Architecture

```text
+-------------------------------------------------------------------+
|                        Docker Compose Stack                       |
|                                                                   |
|  +---------------------------+      +--------------------------+  |
|  |   web (safevault-web)     |      | backup-worker            |  |
|  |   Flask App :5000         |<-----| (safevault-backup-worker)|  |
|  |   Mapped to Host :8082    | waits| Runs every 60 seconds    |  |
|  |   GET /health             | for  | Calls create_backup()    |  |
|  +-------------+-------------+healthy+------------+------------+  |
|                |                                  |               |
|                +----------------+-----------------+               |
|                                 |                                 |
|             +-------------------+-------------------+             |
|             |                                       |             |
|   +---------v----------+                 +----------v---------+   |
|   | Named Volume       |                 | Host Bind Mount    |   |
|   | database-data      |                 | ./backups          |   |
|   | Mounted at /data   |                 | Mounted at /backups|   |
|   | (safevault.db)     |                 | (.db + .sha256)    |   |
|   +--------------------+                 +--------------------+   |
+-------------------------------------------------------------------+
```

---

## 3. Project Folder Structure

```text
Safe_Vault/
├── app.py                   # Flask web server, API endpoints, and health check
├── backup_manager.py        # SQLite CRUD, online backups, SHA-256 & integrity checks, restore
├── backup_worker.py         # Automated 60-second background backup worker
├── Dockerfile               # Python 3.11-slim container image for web & worker
├── docker-compose.yml       # Multi-container orchestration (web + backup-worker)
├── requirements.txt         # Minimal Python dependencies (Flask)
├── .gitignore               # Ignores caches, temp DBs, and backup artifacts
├── templates/
│   └── index.html           # Dark navy responsive web dashboard
├── static/
│   ├── style.css            # Navy/blue/purple UI styling
│   └── app.js               # Dashboard API calls, live refresh, confirmation modals
├── backups/                 # Host folder mounted at /backups in both containers
│   └── .gitkeep
├── tests/
│   ├── __init__.py
│   └── test_safevault.py    # Automated unit & integration tests
└── README.md                # Full documentation & viva guide
```

---

## 4. Prerequisites (Windows 11)

1. **Docker Desktop for Windows** (with WSL 2 backend enabled and Docker Desktop **running**).
2. **Windows PowerShell** (built into Windows 11).
3. *(Optional, only if running tests outside Docker)* Python 3.11+.

---

## 5. Exact Windows PowerShell Commands

Open PowerShell in the `Safe_Vault` folder:

```powershell
cd "C:\Users\mayank jha\Desktop\Safe_Vault"
```

### Build and Start the System

```powershell
docker compose up --build -d
```

> **Note:** If your Docker Desktop setup uses the standalone binary instead of the Compose plugin, use `docker-compose up --build -d`.

### Open the Dashboard

Visit in your browser:
- **Dashboard:** [http://localhost:8082](http://localhost:8082)
- **Health Check:** [http://localhost:8082/health](http://localhost:8082/health)

### Check Container Status & Logs

```powershell
# See running containers and health status
docker compose ps

# Watch automated backup worker logs live (Ctrl+C to exit logs)
docker compose logs -f backup-worker

# View web server logs
docker compose logs -f web
```

### Stop the System Safely

```powershell
# Stops and removes containers ONLY — keeps your database volume and ./backups folder safe!
docker compose down
```

> **IMPORTANT SAFETY RULE:** Never run `docker compose down -v` unless you intentionally want to wipe the `database-data` Docker volume.

---

## 6. How to Run Automated Tests

### Option A: Run Tests Inside Docker (Recommended — Works Even Without Local Python)

```powershell
docker compose run --rm --no-deps web python -m unittest discover -s tests -v
```

### Option B: Run Tests Locally with Python 3.11+

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

---

## 7. How to Demonstrate Disaster Recovery (For College Evaluators)

Follow this 5-step live demo during your project presentation:

1. **Add Student Records:**
   - Open `http://localhost:8082`.
   - Add 2–3 students using the **Add Student Record** form (e.g., *Aarav Sharma*, *Priya Verma*).
   - Point out the **Student Records** counter updating live.
2. **Create & Verify a Backup:**
   - Either click **Create Manual Backup Now** or wait 60 seconds for the `backup-worker` container to create one automatically.
   - Show the **Backup History & Integrity Verification** table: timestamp, file size, SHA-256 checksum, and `Verified (SHA-256 + Integrity)` badge.
   - You can also open the `./backups` folder in Windows Explorer to show the `.db` and `.sha256` files stored on the host!
3. **Simulate Accidental Data Loss:**
   - Click **Simulate Data Loss (Delete All Rows)** and confirm in the dialog.
   - Show evaluators that **Student Records** drops to `0` (`DELETE FROM students;` ran), while the backups remain safe.
4. **Restore from Latest Valid Backup:**
   - Click **Restore Latest Valid Backup** and confirm.
   - SafeVault verifies the SHA-256 checksum and `PRAGMA integrity_check`, restores through a temporary database file, and brings all student records back!
5. **Show Worker Logs & Health Endpoint:**
   - Open `http://localhost:8082/health` to show JSON health monitoring.
   - Run `docker compose logs --tail=15 backup-worker` in PowerShell to show automated 60-second snapshots running independently of the web container.

---

## 8. How the System Works (Beginner-Friendly Explanation)

- **Docker Containers:** Instead of installing Python and services directly on Windows, Docker packages the app into lightweight, isolated Linux boxes (`web` and `backup-worker`) so it runs identically everywhere.
- **Docker Named Volume (`database-data` -> `/data`):** A storage box managed by Docker so the SQLite database survives container restarts.
- **Bind Mount (`./backups` -> `/backups`):** Links your Windows `backups` folder directly into both containers so you can inspect the backup files directly in Windows File Explorer.
- **SQLite Online Backup API (`conn.backup()`):** Simply copying a `.db` file while a web app is using it can create a half-written corrupted copy. SQLite's built-in `backup()` safely locks and copies pages cleanly.
- **SHA-256 Checksum:** A digital fingerprint of the backup file. If even 1 bit changes due to disk corruption or tampering, the SHA-256 fingerprint changes completely and SafeVault refuses to restore it.
- **`PRAGMA integrity_check`:** SQLite's internal health scan that checks B-trees, indexes, and table structure inside the backup file.
- **Temporary-File Restore:** SafeVault never overwrites the live database blindly. It copies the backup to a temporary file, re-verifies it, and then swaps it atomically using `os.replace()`.

---

## 9. Troubleshooting

| Issue | Likely Cause | Fix |
|---|---|---|
| `open //./pipe/docker_engine: The system cannot find the file specified` | Docker Desktop is not running yet | Open **Docker Desktop**, wait until the bottom bar says **Engine running**, then retry `docker compose up --build -d` |
| Port `8082` already in use | Another app is using port 8082 | Change `"8082:5000"` in `docker-compose.yml` to `"8085:5000"` and restart |
| `backup-worker` stays `Created` | It waits for `web` health check | Run `docker compose logs web` to inspect why `web` isn't healthy yet |
| Browser shows old cached UI | Browser cache | Hard refresh with `Ctrl + F5` |

---

## 10. Known Limitations & Future Improvements

This project is an **educational local prototype**, not production-ready. Key limitations and planned improvements include:

1. **No Authentication / Authorization:** Anyone with access to `http://localhost:8082` can add records, simulate data loss, or restore backups. *Future improvement:* Add user login, session management, and role-based access control (RBAC).
2. **Local Backups Only (No Offsite Storage):** Backups live in `./backups` on the same host machine. If the whole disk fails, local backups would also be lost. *Future improvement:* Upload encrypted backups to offsite cloud object storage (e.g., AWS S3, Google Cloud Storage, or Backblaze B2) following the **3-2-1 backup rule**.
3. **Single-Node SQLite Database:** Great for prototypes and small workloads, but high concurrent traffic would benefit from PostgreSQL with streaming replication and point-in-time recovery (PITR).
4. **Unencrypted Backup Files:** Backups are verified with SHA-256 (integrity) but not encrypted at rest (confidentiality). *Future improvement:* Encrypt snapshots with AES-256-GCM before saving.

---

## 11. College Viva Questions & Answers

**Q1: Why did you separate `web` and `backup-worker` into two containers?**  
**A:** Separation of concerns and fault isolation. If the web server crashes or restarts, the backup schedule keeps running independently (and vice versa). It also mirrors real microservices architecture.

**Q2: Why not just use `shutil.copy()` to copy `safevault.db`?**  
**A:** Copying a live SQLite file with standard OS file copy while another process is writing can produce a torn/corrupted database. SQLite's `conn.backup()` API coordinates safe page-level snapshots.

**Q3: Why do you check BOTH SHA-256 and `PRAGMA integrity_check`?**  
**A:** SHA-256 proves the file has not changed since it was created (detects tampering or bit-rot). `PRAGMA integrity_check` proves the SQLite internal database pages and tables are structurally valid.

**Q4: Why restore through a temporary file instead of writing directly over `safevault.db`?**  
**A:** If a failure happens halfway through copying directly onto the live database, the live database would be left half-written and destroyed. Staging and verifying in a temporary file first makes the final `os.replace()` atomic.

**Q5: What happens when you click "Simulate Data Loss"?**  
**A:** It runs `DELETE FROM students;` to erase all student rows while keeping the database schema and backups intact—simulating an accidental `DELETE` query in production.

**Q6: Why does `backup-worker` use `depends_on: condition: service_healthy`?**  
**A:** So Docker Compose waits until the Flask app passes its `/health` endpoint check and initializes the database schema before the worker starts backing it up.
