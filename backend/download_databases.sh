#!/bin/bash
# Auto-download reference databases if missing.
# Called by the pipeline worker before first annotation run.
# Safe to re-run: skips databases that already exist.

set -e
DB_DIR="${1:-/databases}"
LOCK="${DB_DIR}/.download.lock"

mkdir -p "${DB_DIR}"

# Prevent concurrent downloads (multiple workers)
if [ -f "$LOCK" ]; then
    echo "Database download already in progress (lock: $LOCK), waiting..."
    while [ -f "$LOCK" ]; do sleep 5; done
    echo "Lock released, continuing."
    exit 0
fi
trap 'rm -f "$LOCK"' EXIT
echo $$ > "$LOCK"

NEEDED=0

# Check which databases are missing (skani excluded — 30 GB, 16S BLAST is used as fallback)
[ -d "${DB_DIR}/amrfinderplus" ] && [ -f "${DB_DIR}/amrfinderplus/AMRProt" -o -f "${DB_DIR}/amrfinderplus/AMRProt.fa" ] || NEEDED=1
[ -d "${DB_DIR}/genomad_db" ] || NEEDED=1
[ -f "${DB_DIR}/16S/16S_ribosomal_RNA.ndb" ] || NEEDED=1
[ -d "${DB_DIR}/pointfinder_db" ] || NEEDED=1
[ -d "${DB_DIR}/resfinder_db" ] || NEEDED=1
[ -f "${DB_DIR}/Rfam.cm" ] || NEEDED=1

if [ "$NEEDED" = "0" ]; then
    echo "All databases present."
    exit 0
fi

echo "Downloading missing databases to ${DB_DIR}..."

# AMRFinderPlus database
if ! ( [ -d "${DB_DIR}/amrfinderplus" ] && [ -f "${DB_DIR}/amrfinderplus/AMRProt" -o -f "${DB_DIR}/amrfinderplus/AMRProt.fa" ] ); then
    echo "  AMRFinderPlus database..."
    if conda run -n radar amrfinder --update > /tmp/radar_db_amrfinder.log 2>&1; then
        AMRFINDER_BIN_DIR="$(conda run -n radar bash -c 'echo ${CONDA_PREFIX}/bin')"
        ln -sfn "${AMRFINDER_BIN_DIR}/data/latest" "${DB_DIR}/amrfinderplus" 2>/dev/null
        echo "    done"
    else
        echo "    amrfinder --update failed; downloading manually..."
        AMRFINDER_FTP="https://ftp.ncbi.nlm.nih.gov/pathogen/Antimicrobial_resistance/AMRFinderPlus/database/latest"
        mkdir -p "${DB_DIR}/amrfinderplus"
        FILE_LIST=$(curl -sL "${AMRFINDER_FTP}/" | grep -oP 'href="([^"/]+)"' | sed 's/href="//;s/"//' | grep -v '/$')
        for f in $FILE_LIST; do
            curl -sfL "${AMRFINDER_FTP}/${f}" -o "${DB_DIR}/amrfinderplus/${f}" 2>/dev/null || true
        done
        if [ -f "${DB_DIR}/amrfinderplus/AMRProt.fa" ]; then
            conda run -n radar makeblastdb -in "${DB_DIR}/amrfinderplus/AMRProt.fa" -dbtype prot -out "${DB_DIR}/amrfinderplus/AMRProt.fa" >> /tmp/radar_db_amrfinder.log 2>&1 || true
            conda run -n radar makeblastdb -in "${DB_DIR}/amrfinderplus/AMR_CDS.fa" -dbtype nucl -out "${DB_DIR}/amrfinderplus/AMR_CDS.fa" >> /tmp/radar_db_amrfinder.log 2>&1 || true
            for dna_fa in "${DB_DIR}/amrfinderplus"/AMR_DNA-*.fa; do
                [ -f "$dna_fa" ] && conda run -n radar makeblastdb -in "$dna_fa" -dbtype nucl -out "$dna_fa" >> /tmp/radar_db_amrfinder.log 2>&1 || true
            done
            [ -f "${DB_DIR}/amrfinderplus/amr_targets.fa" ] && conda run -n radar makeblastdb -in "${DB_DIR}/amrfinderplus/amr_targets.fa" -dbtype nucl -out "${DB_DIR}/amrfinderplus/amr_targets.fa" >> /tmp/radar_db_amrfinder.log 2>&1 || true
            conda run -n radar hmmpress -f "${DB_DIR}/amrfinderplus/AMR.LIB" >> /tmp/radar_db_amrfinder.log 2>&1 || true
            AMRFINDER_BIN_DIR="$(conda run -n radar bash -c 'echo ${CONDA_PREFIX}/bin')"
            mkdir -p "${AMRFINDER_BIN_DIR}/data"
            ln -sfn "${DB_DIR}/amrfinderplus" "${AMRFINDER_BIN_DIR}/data/latest" 2>/dev/null
            echo "    done (manual)"
        else
            echo "    FAILED"
        fi
    fi
fi

# geNomad database (~3.5 GB)
if [ ! -d "${DB_DIR}/genomad_db" ]; then
    echo "  geNomad database..."
    if conda run -n radar-genomad genomad download-database "${DB_DIR}" > /tmp/radar_db_genomad.log 2>&1; then
        echo "    done"
    else
        echo "    FAILED (see /tmp/radar_db_genomad.log)"
    fi
fi

# skani GTDB sketch database (~30 GB compressed, ~50 GB uncompressed)
# Skipped by default — 16S BLAST is used as fallback for species ID.
# To install manually:
#   curl -L -o skani_gtdb_r226-v0.3.tar.gz http://faust.compbio.cs.cmu.edu/skani-files/skani_gtdb_r226-v0.3.tar.gz
#   tar xzf skani_gtdb_r226-v0.3.tar.gz -C /databases/skani && rm skani_gtdb_r226-v0.3.tar.gz

# NCBI 16S rRNA BLAST database
if [ ! -f "${DB_DIR}/16S/16S_ribosomal_RNA.ndb" ]; then
    echo "  16S rRNA BLAST database..."
    mkdir -p "${DB_DIR}/16S"
    if (cd "${DB_DIR}/16S" && \
        curl -sL -O "https://ftp.ncbi.nlm.nih.gov/blast/db/16S_ribosomal_RNA.tar.gz" \
        && tar xzf 16S_ribosomal_RNA.tar.gz \
        && rm 16S_ribosomal_RNA.tar.gz); then
        echo "    done"
    else
        echo "    FAILED"
    fi
fi

# MOB-suite database
echo "  MOB-suite database..."
conda run -n radar-mobsuite mob_init > /tmp/radar_db_mobsuite.log 2>&1 || echo "    FAILED (will auto-download on first run)"

# PointFinder database
if [ ! -d "${DB_DIR}/pointfinder_db" ]; then
    echo "  PointFinder database..."
    if git clone --quiet https://bitbucket.org/genomicepidemiology/pointfinder_db.git "${DB_DIR}/pointfinder_db" 2>/dev/null; then
        echo "    done"
    else
        echo "    FAILED"
    fi
fi

# ResFinder database
if [ ! -d "${DB_DIR}/resfinder_db" ]; then
    echo "  ResFinder database..."
    if git clone --quiet https://bitbucket.org/genomicepidemiology/resfinder_db.git "${DB_DIR}/resfinder_db" 2>/dev/null; then
        echo "    done"
    else
        echo "    FAILED"
    fi
fi

# Rfam CM database
if [ ! -f "${DB_DIR}/Rfam.cm" ]; then
    echo "  Rfam database..."
    if curl -sL -o "${DB_DIR}/Rfam.cm.gz" "https://ftp.ebi.ac.uk/pub/databases/Rfam/CURRENT/Rfam.cm.gz" \
        && gunzip "${DB_DIR}/Rfam.cm.gz" \
        && conda run -n radar cmpress "${DB_DIR}/Rfam.cm" > /dev/null 2>&1; then
        echo "    done"
    else
        echo "    FAILED"
    fi
fi

# DefenseFinder models
echo "  DefenseFinder models..."
conda run -n radar defense-finder update > /tmp/radar_db_defense.log 2>&1 || echo "    FAILED"

echo "Database download complete."
