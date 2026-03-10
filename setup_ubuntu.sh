#!/usr/bin/env bash
set -euo pipefail

# RADAR - Setup Script (no sudo required)
# Sets up isolated conda environments for the RADAR platform.
# Each bioinformatics tool group gets its own env to avoid dependency conflicts.
# The pipeline calls tools via: conda run -n <env> <tool> ...
#
# Environments:
#   radar            - Core platform (Python, Node, PostgreSQL, Redis, pip tools)
#   radar-qc         - bbmap (bbduk), fastqc
#   radar-assembly   - unicycler
#   radar-busco      - busco, quast
#   radar-amr        - AMRFinderPlus
#   radar-plasmid    - MOB-suite
#   radar-sra        - sra-tools
#
# Ports are derived from your UID so multiple users can run on the same machine:
#   Frontend:   UID + 3000
#   Backend:    UID + 8000
#   PostgreSQL: UID + 5432
#   Redis:      UID + 6379
#
# Prerequisites: mamba (Miniforge recommended)
#
# Usage:
#   chmod +x setup_ubuntu.sh
#   ./setup_ubuntu.sh

PYTHON_VERSION="3.11"
NODE_VERSION="20"

ENVS=(radar radar-qc radar-assembly radar-busco radar-amr radar-plasmid radar-sra)

# Derive per-user ports from UID
USER_UID=$(id -u)
PORT_FRONTEND=$((USER_UID + 3000))
PORT_BACKEND=$((USER_UID + 8000))
PORT_PG=$((USER_UID + 5432))
PORT_REDIS=$((USER_UID + 6379))

echo "============================================"
echo "  RADAR Setup (no sudo required)"
echo "============================================"
echo ""
echo "  User: $(whoami) (UID ${USER_UID})"
echo "  Ports: frontend=${PORT_FRONTEND} backend=${PORT_BACKEND} pg=${PORT_PG} redis=${PORT_REDIS}"

# --------------------------------------------------------------------------
# 1. Check mamba
# --------------------------------------------------------------------------
if ! command -v mamba &> /dev/null; then
    echo "ERROR: mamba not found. Install Miniforge (no sudo needed):"
    echo ""
    echo "  curl -L -O https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh"
    echo "  bash Miniforge3-Linux-x86_64.sh"
    echo ""
    exit 1
fi

# --------------------------------------------------------------------------
# 2. Check for existing environments
# --------------------------------------------------------------------------
EXISTING=()
for env in "${ENVS[@]}"; do
    if mamba env list | grep -q "^${env} "; then
        EXISTING+=("${env}")
    fi
done

if [ ${#EXISTING[@]} -gt 0 ]; then
    echo ""
    echo "  Existing environments found: ${EXISTING[*]}"
    read -rp "  Remove and recreate them? [y/N] " answer
    if [[ "${answer}" =~ ^[Yy]$ ]]; then
        for env in "${EXISTING[@]}"; do
            echo "  Removing ${env}..."
            mamba env remove -n "${env}" -y 2>/dev/null || true
        done
    else
        echo "Aborting setup."
        exit 0
    fi
fi

# --------------------------------------------------------------------------
# 3. Core environment
# --------------------------------------------------------------------------
echo ""
echo "[1/7] Creating core environment 'radar'..."
mamba create -n radar -y \
    python="${PYTHON_VERSION}" \
    nodejs="${NODE_VERSION}" \
    postgresql=16 \
    redis-server \
    gcc_linux-64 \
    gxx_linux-64 \
    libpq \
    cairo \
    pango \
    gdk-pixbuf \
    libffi \
    pkg-config \
    viennarna \
    -c conda-forge

# --------------------------------------------------------------------------
# 4. Tool environments (installed in parallel where possible)
# --------------------------------------------------------------------------
echo ""
echo "[2/7] Creating tool environments..."

mamba create -n radar-qc -y -c bioconda -c conda-forge \
    bbmap fastqc &
PID_QC=$!

mamba create -n radar-assembly -y -c bioconda -c conda-forge \
    unicycler &
PID_ASM=$!

mamba create -n radar-busco -y -c bioconda -c conda-forge \
    busco quast &
PID_BUSCO=$!

(mamba create -n radar-amr -y -c bioconda -c conda-forge hmmer blast curl \
    && curl -sL https://api.github.com/repos/ncbi/amr/releases/latest \
        | grep -oP '"browser_download_url":\s*"\K[^"]+' \
        | xargs curl -sL -o /tmp/amrfinder.tar.gz \
    && tar xzf /tmp/amrfinder.tar.gz -C "$(conda run -n radar-amr bash -c 'dirname $(which hmmsearch)')/") &
PID_AMR=$!

(mamba create -n radar-plasmid -y python=3.11 -c conda-forge \
    && conda run -n radar-plasmid pip install --quiet mob_suite) &
PID_PLASMID=$!

mamba create -n radar-sra -y -c bioconda -c conda-forge \
    sra-tools &
PID_SRA=$!

FAIL=0
for pid_name in QC:$PID_QC ASM:$PID_ASM BUSCO:$PID_BUSCO AMR:$PID_AMR PLASMID:$PID_PLASMID SRA:$PID_SRA; do
    name="${pid_name%%:*}"
    pid="${pid_name##*:}"
    if wait "${pid}"; then
        echo "  ✓ radar-${name,,} done"
    else
        echo "  ✗ radar-${name,,} FAILED"
        FAIL=1
    fi
done

if [ "${FAIL}" -eq 1 ]; then
    echo "ERROR: One or more tool environments failed to install. Check output above."
    exit 1
fi

# --------------------------------------------------------------------------
# 5. Update AMRFinderPlus database
# --------------------------------------------------------------------------
echo ""
echo "[3/7] Updating AMRFinderPlus database..."
conda run -n radar-amr amrfinder --update \
    || echo "  WARNING: AMRFinderPlus DB update failed (may need manual setup)"

# --------------------------------------------------------------------------
# 6. Pip-based tools in core env
# --------------------------------------------------------------------------
echo ""
echo "[4/7] Installing pip-based tools (MobileElementFinder, OSTIR)..."
eval "$(conda shell.bash hook)"
conda activate radar
pip install --quiet "setuptools<81" MobileElementFinder OSTIR

# --------------------------------------------------------------------------
# 7. Python backend dependencies
# --------------------------------------------------------------------------
echo ""
echo "[5/7] Installing Python backend dependencies..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pip install --quiet -r "${SCRIPT_DIR}/backend/requirements.txt"

# --------------------------------------------------------------------------
# 8. Node.js frontend dependencies
# --------------------------------------------------------------------------
echo ""
echo "[6/7] Installing Node.js frontend dependencies..."
cd "${SCRIPT_DIR}/frontend"
npm install --silent
cd "${SCRIPT_DIR}"

# --------------------------------------------------------------------------
# 9. BPROM binary + data directories
# --------------------------------------------------------------------------
echo ""
echo "[7/7] Final setup..."

if [ -f /tmp/bprom ]; then
    CONDA_BIN="$(dirname "$(which python)")"
    cp /tmp/bprom "${CONDA_BIN}/bprom"
    chmod +x "${CONDA_BIN}/bprom"
    echo "  BPROM binary installed to ${CONDA_BIN}/bprom"
else
    echo "  WARNING: /tmp/bprom not found. Copy the BPROM binary to /tmp/bprom and re-run, or install manually."
fi

mkdir -p "${SCRIPT_DIR}/data/uploads" "${SCRIPT_DIR}/data/results" "${SCRIPT_DIR}/data/pgdata"

# --------------------------------------------------------------------------
# Save port config for start/stop scripts
# --------------------------------------------------------------------------
cat > "${SCRIPT_DIR}/data/ports.env" << EOF
PORT_FRONTEND=${PORT_FRONTEND}
PORT_BACKEND=${PORT_BACKEND}
PORT_PG=${PORT_PG}
PORT_REDIS=${PORT_REDIS}
EOF

# --------------------------------------------------------------------------
# Create helper scripts for running without Docker
# --------------------------------------------------------------------------
cat > "${SCRIPT_DIR}/start_dev.sh" << 'DEVEOF'
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/data"

# Load port configuration
source "${DATA_DIR}/ports.env"

eval "$(conda shell.bash hook)"
conda activate radar

echo ""
echo "  Ports: frontend=${PORT_FRONTEND} backend=${PORT_BACKEND} pg=${PORT_PG} redis=${PORT_REDIS}"
echo ""

# Start PostgreSQL
if ! pg_isready -h localhost -p "${PORT_PG}" -q 2>/dev/null; then
    echo "Starting PostgreSQL on port ${PORT_PG}..."
    if [ ! -f "${DATA_DIR}/pgdata/PG_VERSION" ]; then
        initdb -D "${DATA_DIR}/pgdata" --auth=trust
    fi
    pg_ctl -D "${DATA_DIR}/pgdata" -l "${DATA_DIR}/pg.log" -o "-p ${PORT_PG} -k /tmp" start
    sleep 1
    createdb -h localhost -p "${PORT_PG}" radar 2>/dev/null || true
fi

# Start Redis
if ! redis-cli -p "${PORT_REDIS}" ping &>/dev/null; then
    echo "Starting Redis on port ${PORT_REDIS}..."
    redis-server --daemonize yes --port "${PORT_REDIS}"
fi

echo ""
echo "PostgreSQL: localhost:${PORT_PG} (database: radar)"
echo "Redis:      localhost:${PORT_REDIS}"
echo ""

export RADAR_DATABASE_URL="postgresql://$(whoami)@localhost:${PORT_PG}/radar"
export RADAR_REDIS_URL="redis://localhost:${PORT_REDIS}/0"
export RADAR_UPLOAD_DIR="${DATA_DIR}/uploads"
export RADAR_RESULTS_DIR="${DATA_DIR}/results"

echo "Starting Celery worker..."
cd "${SCRIPT_DIR}/backend"
celery -A app.celery_app worker --loglevel=info &
CELERY_PID=$!

echo "Starting backend on port ${PORT_BACKEND}..."
uvicorn app.main:app --reload --port "${PORT_BACKEND}" &
BACKEND_PID=$!

echo "Starting frontend on port ${PORT_FRONTEND}..."
cd "${SCRIPT_DIR}/frontend"
NEXT_PUBLIC_BACKEND_PORT="${PORT_BACKEND}" PORT="${PORT_FRONTEND}" npm run dev &
FRONTEND_PID=$!

echo ""
echo "============================================"
echo "  RADAR is running!"
echo "  Frontend: http://localhost:${PORT_FRONTEND}"
echo "  Backend:  http://localhost:${PORT_BACKEND}"
echo "  Press Ctrl+C to stop all services"
echo "============================================"

trap "kill $CELERY_PID $BACKEND_PID $FRONTEND_PID 2>/dev/null; pg_ctl -D '${DATA_DIR}/pgdata' stop 2>/dev/null; redis-cli -p ${PORT_REDIS} shutdown 2>/dev/null; echo 'Stopped.'" EXIT
wait
DEVEOF
chmod +x "${SCRIPT_DIR}/start_dev.sh"

cat > "${SCRIPT_DIR}/stop_dev.sh" << 'STOPEOF'
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "${SCRIPT_DIR}/data/ports.env"

eval "$(conda shell.bash hook)"
conda activate radar

pg_ctl -D "${SCRIPT_DIR}/data/pgdata" stop 2>/dev/null && echo "PostgreSQL stopped." || echo "PostgreSQL not running."
redis-cli -p "${PORT_REDIS}" shutdown 2>/dev/null && echo "Redis stopped." || echo "Redis not running."
pkill -f "celery.*radar" 2>/dev/null && echo "Celery stopped." || true
pkill -f "uvicorn.*app.main" 2>/dev/null && echo "Backend stopped." || true
echo "Done."
STOPEOF
chmod +x "${SCRIPT_DIR}/stop_dev.sh"

# --------------------------------------------------------------------------
# Done
# --------------------------------------------------------------------------
echo ""
echo "============================================"
echo "  RADAR setup complete!"
echo "============================================"
echo ""
echo "  Environments installed:"
for env in "${ENVS[@]}"; do
    echo "    - ${env}"
done
echo ""
echo "  Your ports (UID ${USER_UID}):"
echo "    Frontend:   http://localhost:${PORT_FRONTEND}"
echo "    Backend:    http://localhost:${PORT_BACKEND}"
echo "    PostgreSQL: localhost:${PORT_PG}"
echo "    Redis:      localhost:${PORT_REDIS}"
echo ""
echo "  Start all services:"
echo "    ./start_dev.sh"
echo ""
echo "  Stop all services:"
echo "    ./stop_dev.sh"
echo ""
echo "  Pipeline calls tools via: conda run -n <env> <tool>"
echo "    e.g. conda run -n radar-qc bbduk.sh ..."
echo "         conda run -n radar-assembly unicycler ..."
echo "         conda run -n radar-amr amrfinder ..."
echo ""
