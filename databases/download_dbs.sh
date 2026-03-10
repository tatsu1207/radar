#!/usr/bin/env bash
#
# download_dbs.sh
# Download and update reference databases required by RADAR.
#
# Usage:
#   chmod +x databases/download_dbs.sh
#   ./databases/download_dbs.sh
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_DIR="${SCRIPT_DIR}"

echo "============================================"
echo " RADAR - Reference Database Download Script"
echo "============================================"
echo ""
echo "Databases will be stored in: ${DB_DIR}"
echo ""

# -------------------------------------------------------------------
# AMRFinderPlus Database
# -------------------------------------------------------------------
echo "[1/3] Updating AMRFinderPlus database..."
AMRFINDER_DB_DIR="${DB_DIR}/amrfinderplus"
mkdir -p "${AMRFINDER_DB_DIR}"

if command -v amrfinder_update &> /dev/null; then
    amrfinder_update -d "${AMRFINDER_DB_DIR}"
elif command -v amrfinder &> /dev/null; then
    amrfinder --update --database "${AMRFINDER_DB_DIR}"
else
    echo "  AMRFinderPlus not found in PATH. Attempting download via Docker..."
    docker run --rm -v "${AMRFINDER_DB_DIR}:/db" \
        ncbi/amr:latest \
        amrfinder_update -d /db
fi
echo "  AMRFinderPlus database updated successfully."
echo ""

# -------------------------------------------------------------------
# ABRicate Databases
# -------------------------------------------------------------------
echo "[2/3] Updating ABRicate databases..."

ABRICATE_DBS=("card" "resfinder" "vfdb" "plasmidfinder" "megares")

if command -v abricate &> /dev/null; then
    for db_name in "${ABRICATE_DBS[@]}"; do
        echo "  Updating ABRicate database: ${db_name}..."
        abricate-get_db --db "${db_name}" --force
    done
else
    echo "  ABRicate not found in PATH. Attempting download via Docker..."
    for db_name in "${ABRICATE_DBS[@]}"; do
        echo "  Updating ABRicate database: ${db_name}..."
        ABRICATE_DB_DIR="${DB_DIR}/abricate/${db_name}"
        mkdir -p "${ABRICATE_DB_DIR}"
        docker run --rm -v "${DB_DIR}/abricate:/abricate_db" \
            staphb/abricate:latest \
            abricate-get_db --db "${db_name}" --force
    done
fi
echo "  ABRicate databases updated successfully."
echo ""

# -------------------------------------------------------------------
# MOB-suite Database
# -------------------------------------------------------------------
echo "[3/3] Updating MOB-suite database..."
MOBSUITE_DB_DIR="${DB_DIR}/mob-suite"
mkdir -p "${MOBSUITE_DB_DIR}"

if command -v mob_init &> /dev/null; then
    mob_init --database_directory "${MOBSUITE_DB_DIR}" --force
else
    echo "  MOB-suite not found in PATH. Attempting download via Docker..."
    docker run --rm -v "${MOBSUITE_DB_DIR}:/db" \
        kbessonov/mob_suite:latest \
        mob_init --database_directory /db --force
fi
echo "  MOB-suite database updated successfully."
echo ""

# -------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------
echo "============================================"
echo " All databases downloaded successfully."
echo "============================================"
echo ""
echo "Database locations:"
echo "  AMRFinderPlus : ${AMRFINDER_DB_DIR}"
echo "  ABRicate      : ${DB_DIR}/abricate/"
echo "  MOB-suite     : ${MOBSUITE_DB_DIR}"
echo ""
echo "You can now start RADAR with: docker compose up -d"
