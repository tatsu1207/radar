#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/data"
PID_FILE="${DATA_DIR}/pids.env"

source "${DATA_DIR}/ports.env"

eval "$(conda shell.bash hook)"
conda activate radar

# Stop services using saved PIDs
if [ -f "${PID_FILE}" ]; then
    source "${PID_FILE}"
    kill "${CELERY_PID:-}" 2>/dev/null && echo "Celery pipeline worker stopped." || true
    kill "${CELERY_DEFAULT_PID:-}" 2>/dev/null && echo "Celery default worker stopped." || true
    kill "${BACKEND_PID:-}" 2>/dev/null && echo "Backend stopped." || true
    kill "${FRONTEND_PID:-}" 2>/dev/null && echo "Frontend stopped." || true
    rm -f "${PID_FILE}"
fi

# Fallback: kill by process name
pkill -f "celery.*app.celery_app" 2>/dev/null || true
pkill -f "uvicorn.*app.main" 2>/dev/null || true
pkill -f "next-router-worker" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true

# Stop PostgreSQL and Redis
pg_ctl -D "${DATA_DIR}/pgdata" stop 2>/dev/null && echo "PostgreSQL stopped." || echo "PostgreSQL not running."
redis-cli -p "${PORT_REDIS}" shutdown 2>/dev/null && echo "Redis stopped." || echo "Redis not running."

echo "Done."
