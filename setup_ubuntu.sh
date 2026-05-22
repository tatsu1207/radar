#!/usr/bin/env bash
set -euo pipefail

# RADAR - Setup Script (no sudo required)
# Sets up isolated conda environments for the RADAR platform.
# Each bioinformatics tool group gets its own env to avoid dependency conflicts.
# The pipeline calls tools via: conda run -n <env> <tool> ...
#
# Environments:
#   radar            - Core platform (Python, Node, PostgreSQL, Redis, pip tools)
#   radar-qc         - bbmap (bbduk), fastqc, filtlong
#   radar-assembly   - unicycler
#   radar-busco      - quast (QUAST needs Python 3.6 from bioconda)
#   radar-busco5     - busco v6 (installed from gitlab, needs Python 3.10+)
#   radar-amr        - AMRFinderPlus
#   radar-plasmid    - MOB-suite (mob_recon, mob_typer)
#   radar-genomad    - geNomad (prophage/plasmid detection)
#   radar-skani      - skani (fast ANI species screening)
#   radar-mlst       - mlst (multi-locus sequence typing)
#   radar-integron   - IntegronFinder
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

ENVS=(radar radar-qc radar-assembly radar-bakta radar-busco radar-busco5 radar-amr radar-resfinder radar-rgi radar-plasmid radar-genomad radar-skani radar-mlst radar-integron radar-serotype radar-snippy radar-pangenome radar-tree radar-sra radar-crispr radar-defense radar-ice)

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
    bbmap fastqc filtlong &
PID_QC=$!

mamba create -n radar-assembly -y -c bioconda -c conda-forge \
    spades flye medaka polypolish bwa &
PID_ASM=$!

mamba create -n radar-busco -y -c bioconda -c conda-forge \
    quast &
PID_BUSCO=$!

(mamba create -n radar-busco5 -y python=3.10 hmmer prodigal bbmap -c bioconda -c conda-forge \
    && conda run -n radar-busco5 pip install --quiet git+https://gitlab.com/ezlab/busco.git pandas biopython requests) &
PID_BUSCO5=$!

(mamba create -n radar-amr -y -c bioconda -c conda-forge hmmer blast curl \
    && curl -sL https://api.github.com/repos/ncbi/amr/releases/latest \
        | grep -oP '"browser_download_url":\s*"\K[^"]+' \
        | xargs curl -sL -o /tmp/amrfinder.tar.gz \
    && tar xzf /tmp/amrfinder.tar.gz -C "$(conda run -n radar-amr bash -c 'dirname $(which hmmsearch)')/") &
PID_AMR=$!

(mamba create -n radar-plasmid -y python=3.11 -c conda-forge \
    && conda run -n radar-plasmid pip install --quiet mob_suite) &
PID_PLASMID=$!

(mamba create -n radar-genomad -y python=3.10 -c conda-forge \
    && conda run -n radar-genomad pip install --quiet genomad) &
PID_GENOMAD=$!

mamba create -n radar-skani -y -c bioconda -c conda-forge \
    skani &
PID_SKANI=$!

mamba create -n radar-mlst -y -c bioconda -c conda-forge \
    mlst &
PID_MLST=$!

(mamba create -n radar-integron -y -c bioconda -c conda-forge \
    integron_finder) &
PID_INTEGRON=$!

mamba create -n radar-sra -y -c bioconda -c conda-forge \
    sra-tools &
PID_SRA=$!

(mamba create -n radar-bakta -y -c bioconda -c conda-forge \
    bakta) &
PID_BAKTA=$!

(mamba create -n radar-resfinder -y python=3.11 -c conda-forge \
    && mamba run -n radar-resfinder pip install resfinder) &
PID_RESFINDER=$!

(mamba create -n radar-rgi -y -c bioconda -c conda-forge \
    rgi) &
PID_RGI=$!

(mamba create -n radar-serotype -y -c bioconda -c conda-forge \
    sistr_cmd kleborate) &
PID_SEROTYPE=$!

(mamba create -n radar-snippy -y -c bioconda -c conda-forge \
    snippy gubbins fasttree iqtree) &
PID_SNIPPY=$!

(mamba create -n radar-pangenome -y -c bioconda -c conda-forge \
    panaroo) &
PID_PANGENOME=$!

(mamba create -n radar-tree -y -c bioconda -c conda-forge \
    mashtree fasttree iqtree) &
PID_TREE=$!

(mamba create -n radar-crispr -y -c bioconda -c conda-forge \
    crisprcasfinder) &
PID_CRISPR=$!

(mamba create -n radar-defense -y python=3.11 -c conda-forge \
    && mamba run -n radar-defense pip install mdmparis-defense-finder) &
PID_DEFENSE=$!

(mamba create -n radar-ice -y -c bioconda -c conda-forge \
    blast) &
PID_ICE=$!

FAIL=0
for pid_name in QC:$PID_QC ASM:$PID_ASM BUSCO:$PID_BUSCO BUSCO5:$PID_BUSCO5 AMR:$PID_AMR PLASMID:$PID_PLASMID GENOMAD:$PID_GENOMAD SKANI:$PID_SKANI MLST:$PID_MLST INTEGRON:$PID_INTEGRON SRA:$PID_SRA BAKTA:$PID_BAKTA RESFINDER:$PID_RESFINDER RGI:$PID_RGI SEROTYPE:$PID_SEROTYPE SNIPPY:$PID_SNIPPY PANGENOME:$PID_PANGENOME TREE:$PID_TREE CRISPR:$PID_CRISPR DEFENSE:$PID_DEFENSE ICE:$PID_ICE; do
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
echo "[3/7] Updating databases (AMRFinderPlus, geNomad)..."
conda run -n radar-amr amrfinder --update \
    || echo "  WARNING: AMRFinderPlus DB update failed (may need manual setup)"

echo "  Downloading geNomad database..."
conda run -n radar-genomad genomad download-database "${SCRIPT_DIR}/databases" \
    || echo "  WARNING: geNomad DB download failed (may need manual setup)"

echo "  Downloading skani GTDB sketch database..."
mkdir -p "${SCRIPT_DIR}/databases/skani"
cd "${SCRIPT_DIR}/databases/skani"
curl -L -o skani-gtdb.tar.gz "https://zenodo.org/records/10890155/files/skani-gtdb-r220-sketch.tar.gz" \
    && tar xzf skani-gtdb.tar.gz && rm skani-gtdb.tar.gz \
    || echo "  WARNING: skani DB download failed"
cd "${SCRIPT_DIR}"

echo "  Downloading NCBI 16S rRNA BLAST database..."
mkdir -p "${SCRIPT_DIR}/databases/16S"
cd "${SCRIPT_DIR}/databases/16S"
conda run -n radar-amr python3 -c "
import urllib.request, os
f = '16S_ribosomal_RNA.tar.gz'
urllib.request.urlretrieve('https://ftp.ncbi.nlm.nih.gov/blast/db/' + f, f)
os.system('tar xzf ' + f)
os.remove(f)
" || echo "  WARNING: 16S DB download failed (may need manual setup)"
cd "${SCRIPT_DIR}"

# --------------------------------------------------------------------------
# 6. Pip-based tools in core env
# --------------------------------------------------------------------------
echo ""
echo "[4/7] Installing pip-based tools (MobileElementFinder, OSTIR, ResFinder)..."
eval "$(conda shell.bash hook)"
conda activate radar
pip install --quiet "setuptools<81" MobileElementFinder OSTIR resfinder

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

CONDA_BIN="$(dirname "$(which python)")"
if [ -d /tmp/bprom ]; then
    # BPROM distribution directory (contains linux/bprom binary and bprom_data/)
    cp /tmp/bprom/linux/bprom "${CONDA_BIN}/bprom"
    chmod +x "${CONDA_BIN}/bprom"
    cp /tmp/bprom/bprom_data/* "${CONDA_BIN}/"
    echo "  BPROM binary + data files installed to ${CONDA_BIN}/"
elif [ -f /tmp/bprom ]; then
    # Single binary file
    cp /tmp/bprom "${CONDA_BIN}/bprom"
    chmod +x "${CONDA_BIN}/bprom"
    echo "  BPROM binary installed to ${CONDA_BIN}/bprom"
    echo "  WARNING: BPROM data files (bs.list, five.mat, ldfb.tss) not found."
    echo "           Copy them to ${CONDA_BIN}/ for promoter analysis to work."
else
    echo "  WARNING: /tmp/bprom not found. Copy the BPROM directory to /tmp/bprom and re-run."
    echo "           Expected: /tmp/bprom/linux/bprom (binary) and /tmp/bprom/bprom_data/ (data files)"
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
