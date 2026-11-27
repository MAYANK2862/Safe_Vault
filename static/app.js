(function () {
  "use strict";

  const initialPayloadEl = document.getElementById("initial-dashboard-data");
  let state = initialPayloadEl ? JSON.parse(initialPayloadEl.textContent) : null;
  let pendingConfirmAction = null;

  const elements = {
    healthBadge: document.getElementById("healthBadge"),
    healthText: document.getElementById("healthText"),
    refreshBtn: document.getElementById("refreshBtn"),
    alertBanner: document.getElementById("alertBanner"),
    alertTitle: document.getElementById("alertTitle"),
    alertMessage: document.getElementById("alertMessage"),
    alertClose: document.getElementById("alertClose"),
    statStudentCount: document.getElementById("statStudentCount"),
    statBackupCount: document.getElementById("statBackupCount"),
    statLatestStatus: document.getElementById("statLatestStatus"),
    statLatestTime: document.getElementById("statLatestTime"),
    statWorkerInterval: document.getElementById("statWorkerInterval"),
    statSyncTime: document.getElementById("statSyncTime"),
    studentsBadge: document.getElementById("studentsBadge"),
    backupsBadge: document.getElementById("backupsBadge"),
    studentsTableBody: document.getElementById("studentsTableBody"),
    studentsEmptyState: document.getElementById("studentsEmptyState"),
    backupsTableBody: document.getElementById("backupsTableBody"),
    backupsEmptyState: document.getElementById("backupsEmptyState"),
    studentForm: document.getElementById("studentForm"),
    addStudentBtn: document.getElementById("addStudentBtn"),
    manualBackupBtn: document.getElementById("manualBackupBtn"),
    restoreLatestBtn: document.getElementById("restoreLatestBtn"),
    simulateLossBtn: document.getElementById("simulateLossBtn"),
    confirmModal: document.getElementById("confirmModal"),
    modalTitle: document.getElementById("modalTitle"),
    modalMessage: document.getElementById("modalMessage"),
    modalCancelBtn: document.getElementById("modalCancelBtn"),
    modalConfirmBtn: document.getElementById("modalConfirmBtn"),
  };

  function showAlert(type, title, message) {
    elements.alertBanner.classList.remove("hidden", "alert-success", "alert-error");
    elements.alertBanner.classList.add(type === "error" ? "alert-error" : "alert-success");
    elements.alertTitle.textContent = title;
    elements.alertMessage.textContent = message;
  }

  function hideAlert() {
    elements.alertBanner.classList.add("hidden");
  }

  function formatBytes(bytes) {
    if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  }

  function createCell(text, className) {
    const td = document.createElement("td");
    td.textContent = text;
    if (className) td.className = className;
    return td;
  }

  function renderStudents(students) {
    elements.studentsTableBody.innerHTML = "";
    if (!students || students.length === 0) {
      elements.studentsEmptyState.classList.remove("hidden");
      return;
    }

    elements.studentsEmptyState.classList.add("hidden");
    for (const student of students) {
      const tr = document.createElement("tr");
      tr.appendChild(createCell(`#${student.id}`, "mono"));
      tr.appendChild(createCell(student.name));
      tr.appendChild(createCell(student.email));
      tr.appendChild(createCell(student.course));
      tr.appendChild(createCell(student.created_at, "mono"));
      elements.studentsTableBody.appendChild(tr);
    }
  }

  function renderBackups(backups) {
    elements.backupsTableBody.innerHTML = "";
    if (!backups || backups.length === 0) {
      elements.backupsEmptyState.classList.remove("hidden");
      return;
    }

    elements.backupsEmptyState.classList.add("hidden");
    for (const backup of backups) {
      const tr = document.createElement("tr");
      tr.appendChild(createCell(backup.created_at, "mono"));
      tr.appendChild(createCell(backup.filename, "mono"));
      tr.appendChild(createCell(formatBytes(backup.size_bytes)));

      const hashCell = document.createElement("td");
      hashCell.className = "mono";
      hashCell.title = backup.sha256 || "Unavailable";
      hashCell.textContent = backup.sha256 ? `${backup.sha256.slice(0, 16)}...` : "Unavailable";
      tr.appendChild(hashCell);

      const statusCell = document.createElement("td");
      const badge = document.createElement("span");
      badge.className = `status-badge ${backup.valid ? "status-verified" : "status-failed"}`;
      badge.textContent = backup.valid
        ? "Verified (SHA-256 + Integrity)"
        : backup.status;
      badge.title = `Integrity check: ${backup.integrity_message}`;
      statusCell.appendChild(badge);
      tr.appendChild(statusCell);

      const actionCell = document.createElement("td");
      if (backup.valid) {
        const restoreBtn = document.createElement("button");
        restoreBtn.type = "button";
        restoreBtn.className = "btn btn-ghost btn-sm";
        restoreBtn.textContent = "Restore";
        restoreBtn.addEventListener("click", () => {
          openConfirmModal({
            title: "Restore Selected Backup",
            message: `Replace the current student database using verified backup "${backup.filename}"?`,
            confirmLabel: "Restore Backup",
            confirmClass: "btn-success",
            onConfirm: () => triggerRestore(backup.filename),
          });
        });
        actionCell.appendChild(restoreBtn);
      } else {
        const blocked = document.createElement("span");
        blocked.className = "stat-hint";
        blocked.textContent = "Blocked";
        actionCell.appendChild(blocked);
      }
      tr.appendChild(actionCell);

      elements.backupsTableBody.appendChild(tr);
    }
  }

  function renderDashboard(data) {
    state = data;
    elements.statStudentCount.textContent = String(data.student_count);
    elements.statBackupCount.textContent = `${data.backup_count} / ${data.max_backups}`;
    elements.studentsBadge.textContent = `${data.student_count} record(s)`;
    elements.backupsBadge.textContent = `${data.backup_count} snapshot(s)`;
    elements.statWorkerInterval.textContent = `Every ${data.worker_interval_seconds}s`;
    elements.statSyncTime.textContent = `Synced at ${data.server_time}`;

    if (data.latest_backup) {
      elements.statLatestStatus.textContent = data.latest_backup.status;
      elements.statLatestTime.textContent = data.latest_backup.created_at;
    } else {
      elements.statLatestStatus.textContent = "No Backups Yet";
      elements.statLatestTime.textContent = "Create a manual backup or wait 60s";
    }

    const isHealthy = data.health && data.health.status === "healthy";
    elements.healthBadge.classList.toggle("pill-healthy", isHealthy);
    elements.healthBadge.classList.toggle("pill-unhealthy", !isHealthy);
    elements.healthText.textContent = isHealthy ? "System Healthy" : "Database Issue";

    renderStudents(data.students);
    renderBackups(data.backups);
  }

  async function apiRequest(url, options = {}) {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || `Request failed (${response.status})`);
    }
    return payload;
  }

  async function refreshDashboard() {
    try {
      const data = await apiRequest("/api/dashboard");
      renderDashboard(data);
    } catch (err) {
      showAlert("error", "Refresh Failed", err.message);
    }
  }

  function openConfirmModal({ title, message, confirmLabel, confirmClass, onConfirm }) {
    elements.modalTitle.textContent = title;
    elements.modalMessage.textContent = message;
    elements.modalConfirmBtn.textContent = confirmLabel;
    elements.modalConfirmBtn.className = `btn ${confirmClass}`;
    pendingConfirmAction = onConfirm;
    elements.confirmModal.classList.remove("hidden");
  }

  function closeConfirmModal() {
    elements.confirmModal.classList.add("hidden");
    pendingConfirmAction = null;
  }

  async function triggerRestore(filename = null) {
    elements.restoreLatestBtn.disabled = true;
    try {
      const body = filename ? JSON.stringify({ filename }) : JSON.stringify({});
      const result = await apiRequest("/api/backups/restore", { method: "POST", body });
      showAlert("success", "Disaster Recovery Complete", result.message);
      await refreshDashboard();
    } catch (err) {
      showAlert("error", "Restore Failed", err.message);
    } finally {
      elements.restoreLatestBtn.disabled = false;
    }
  }

  async function triggerSimulateLoss() {
    elements.simulateLossBtn.disabled = true;
    try {
      const result = await apiRequest("/api/simulate-loss", { method: "POST" });
      showAlert("success", "Data Loss Simulated", result.message);
      await refreshDashboard();
    } catch (err) {
      showAlert("error", "Simulation Failed", err.message);
    } finally {
      elements.simulateLossBtn.disabled = false;
    }
  }

  elements.studentForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(elements.studentForm);
    const payload = {
      name: String(formData.get("name") || "").trim(),
      email: String(formData.get("email") || "").trim(),
      course: String(formData.get("course") || "").trim(),
    };

    elements.addStudentBtn.disabled = true;
    try {
      const result = await apiRequest("/api/students", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      elements.studentForm.reset();
      showAlert("success", "Student Added", result.message);
      await refreshDashboard();
    } catch (err) {
      showAlert("error", "Validation Error", err.message);
    } finally {
      elements.addStudentBtn.disabled = false;
    }
  });

  elements.manualBackupBtn.addEventListener("click", async () => {
    elements.manualBackupBtn.disabled = true;
    try {
      const result = await apiRequest("/api/backups", { method: "POST" });
      showAlert("success", "Backup Created", result.message);
      await refreshDashboard();
    } catch (err) {
      showAlert("error", "Backup Error", err.message);
    } finally {
      elements.manualBackupBtn.disabled = false;
    }
  });

  elements.restoreLatestBtn.addEventListener("click", () => {
    openConfirmModal({
      title: "Restore Latest Valid Backup",
      message:
        "SafeVault will verify SHA-256 and SQLite integrity on the newest valid backup, stage it in a temporary database file, and restore all student records. Continue?",
      confirmLabel: "Restore Latest Backup",
      confirmClass: "btn-success",
      onConfirm: () => triggerRestore(null),
    });
  });

  elements.simulateLossBtn.addEventListener("click", () => {
    openConfirmModal({
      title: "Simulate Accidental Data Loss",
      message:
        "This will delete ALL student rows from the active SQLite database (table structure and existing backups remain safe). Are you sure you want to simulate data loss?",
      confirmLabel: "Delete Student Rows",
      confirmClass: "btn-danger",
      onConfirm: triggerSimulateLoss,
    });
  });

  elements.refreshBtn.addEventListener("click", refreshDashboard);
  elements.alertClose.addEventListener("click", hideAlert);
  elements.modalCancelBtn.addEventListener("click", closeConfirmModal);
  elements.confirmModal.addEventListener("click", (event) => {
    if (event.target === elements.confirmModal) closeConfirmModal();
  });
  elements.modalConfirmBtn.addEventListener("click", async () => {
    const action = pendingConfirmAction;
    closeConfirmModal();
    if (action) await action();
  });

  if (state) {
    renderDashboard(state);
  }
  setInterval(refreshDashboard, 15000);
})();
