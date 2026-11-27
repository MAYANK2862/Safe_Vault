FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/data/safevault.db \
    BACKUP_DIR=/backups \
    MAX_BACKUPS=10 \
    BACKUP_INTERVAL_SECONDS=60

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /data /backups

EXPOSE 5000

CMD ["python", "app.py"]
