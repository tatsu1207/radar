#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/data"
LOG_DIR="${DATA_DIR}/logs"
PID_FILE="${DATA_DIR}/pids.env"

mkdir -p "${LOG_DIR}"

# Load port configuration
source "${DATA_DIR}/ports.env"

eval "$(conda shell.bash hook)"
conda activate radar

echo ""
echo "  Ports: frontend=${PORT_FRONTEND} backend=${PORT_BACKEND} pg=${PORT_PG} redis=${PORT_REDIS}"
echo ""

# ── PostgreSQL ────────────────────────────────────────────────────────────
if ! pg_isready -h localhost -p "${PORT_PG}" -q 2>/dev/null; then
    echo "Starting PostgreSQL on port ${PORT_PG}..."
    if [ ! -f "${DATA_DIR}/pgdata/PG_VERSION" ]; then
        initdb -D "${DATA_DIR}/pgdata" --auth=trust
    fi
    pg_ctl -D "${DATA_DIR}/pgdata" -l "${LOG_DIR}/pg.log" -o "-p ${PORT_PG} -k /tmp" start
    sleep 1
    createdb -h localhost -p "${PORT_PG}" radar 2>/dev/null || true
else
    echo "PostgreSQL already running on port ${PORT_PG}"
fi

# ── Redis ─────────────────────────────────────────────────────────────────
if ! redis-cli -p "${PORT_REDIS}" ping &>/dev/null; then
    echo "Starting Redis on port ${PORT_REDIS}..."
    redis-server --daemonize yes --port "${PORT_REDIS}" --logfile "${LOG_DIR}/redis.log"
else
    echo "Redis already running on port ${PORT_REDIS}"
fi

export RADAR_DATABASE_URL="postgresql://$(whoami)@localhost:${PORT_PG}/radar"
export RADAR_REDIS_URL="redis://localhost:${PORT_REDIS}/0"
export RADAR_UPLOAD_DIR="${DATA_DIR}/uploads"
export RADAR_RESULTS_DIR="${DATA_DIR}/results"
export TSS_DATA="$(dirname "$(which python)")"
export RADAR_GENOMAD_DB="${SCRIPT_DIR}/databases/genomad_db"
export RADAR_16S_DB="${SCRIPT_DIR}/databases/16S/16S_ribosomal_RNA"
export RADAR_SKANI_DB="${SCRIPT_DIR}/databases/skani"
export RADAR_RFAM_CM="${SCRIPT_DIR}/databases/Rfam.cm"
export RADAR_POINTFINDER_DB="${SCRIPT_DIR}/databases/pointfinder_db"
export RADAR_RESFINDER_DB="${SCRIPT_DIR}/databases/resfinder_db"

# ── Celery workers ────────────────────────────────────────────────────────
cd "${SCRIPT_DIR}/backend"
# Pipeline worker: one job at a time (bioinformatics tools use many threads/RAM)
echo "Starting Celery pipeline worker (concurrency=1)..."
nohup celery -A app.celery_app worker --loglevel=info --pool=threads --concurrency=1 \
    -Q pipeline -n pipeline@%h \
    >> "${LOG_DIR}/celery.log" 2>&1 &
CELERY_PID=$!
# Default worker: SRA downloads, BV-BRC fetches, etc.
echo "Starting Celery default worker..."
nohup celery -A app.celery_app worker --loglevel=info --pool=threads --concurrency=4 \
    -Q celery -n default@%h \
    >> "${LOG_DIR}/celery_default.log" 2>&1 &
CELERY_DEFAULT_PID=$!

# ── Backend ───────────────────────────────────────────────────────────────
echo "Starting backend on port ${PORT_BACKEND}..."
nohup uvicorn app.main:app --reload --host 0.0.0.0 --port "${PORT_BACKEND}" \
    >> "${LOG_DIR}/backend.log" 2>&1 &
BACKEND_PID=$!

# ── Frontend ──────────────────────────────────────────────────────────────
echo "Starting frontend on port ${PORT_FRONTEND}..."
cd "${SCRIPT_DIR}/frontend"
nohup env NEXT_PUBLIC_BACKEND_PORT="${PORT_BACKEND}" PORT="${PORT_FRONTEND}" HOSTNAME="0.0.0.0" npm run dev \
    >> "${LOG_DIR}/frontend.log" 2>&1 &
FRONTEND_PID=$!

# ── Save PIDs ─────────────────────────────────────────────────────────────
cat > "${PID_FILE}" << EOF
CELERY_PID=${CELERY_PID}
BACKEND_PID=${BACKEND_PID}
FRONTEND_PID=${FRONTEND_PID}
EOF

echo ""
echo "============================================"
echo "  RADAR is running!"
echo "============================================"
echo ""
echo "  Frontend: http://localhost:${PORT_FRONTEND}"
echo "  Backend:  http://localhost:${PORT_BACKEND}"
echo "  PostgreSQL: localhost:${PORT_PG}"
echo "  Redis:      localhost:${PORT_REDIS}"
echo ""
echo "  Logs:     ${LOG_DIR}/"
echo "  Stop:     ./stop_dev.sh"
echo ""
