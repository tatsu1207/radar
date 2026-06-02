#!/bin/bash
# Worker entrypoint: ensure databases are ready, then start Celery.

DB_DIR="/databases"
SCRIPT_DIR="$(dirname "$0")"

# Restore AMRFinderPlus symlink if needed
if [ -d "${DB_DIR}/amrfinderplus" ]; then
    CONDA_BIN="$(conda run -n radar bash -c 'echo $CONDA_PREFIX/bin' 2>/dev/null)"
    if [ -n "$CONDA_BIN" ] && [ ! -e "${CONDA_BIN}/data/latest" ]; then
        mkdir -p "${CONDA_BIN}/data"
        ln -sfn "${DB_DIR}/amrfinderplus" "${CONDA_BIN}/data/latest"
        echo "Restored AMRFinderPlus symlink"
    fi
fi

# Download missing databases in background (non-blocking)
if [ -f "${SCRIPT_DIR}/download_databases.sh" ]; then
    # Quick check: skip if key databases already exist
    if [ ! -d "${DB_DIR}/genomad_db" ] || [ ! -f "${DB_DIR}/16S/16S_ribosomal_RNA.ndb" ]; then
        echo "Downloading reference databases in background..."
        bash "${SCRIPT_DIR}/download_databases.sh" "${DB_DIR}" &
    else
        echo "Reference databases present."
    fi
fi

# Start Celery worker
exec "$@"
