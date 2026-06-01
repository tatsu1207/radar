#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# RADAR - Install Script
# ============================================================================
# Installs bioinformatics tools: one base `radar` env plus separate envs only
# for tools with incompatible dependencies.
# Requires: mamba (Miniforge)
# Usage: ./install.sh [-d /path/to/databases] [-t threads]
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_DIR="${SCRIPT_DIR}/databases"
THREADS=4
ENVS_ONLY=0

while getopts "d:t:eh" opt; do
    case $opt in
        d) DB_DIR="$OPTARG" ;;
        t) THREADS="$OPTARG" ;;
        e) ENVS_ONLY=1 ;;
        h)
            echo "Usage: $0 [-d database_dir] [-t threads] [-e]"
            echo "  -d  Database directory (default: ./databases)"
            echo "  -t  Threads for database indexing (default: 4)"
            echo "  -e  Envs only (skip database downloads)"
            exit 0
            ;;
        *) exit 1 ;;
    esac
done

echo "============================================"
echo "  RADAR Install"
echo "============================================"
echo "  Database dir: ${DB_DIR}"
echo ""

# --------------------------------------------------------------------------
# 1. Check mamba
# --------------------------------------------------------------------------
if ! command -v mamba &> /dev/null; then
    echo "ERROR: mamba not found. Install Miniforge first:"
    echo ""
    echo "  curl -L -O https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh"
    echo "  bash Miniforge3-Linux-x86_64.sh"
    echo ""
    exit 1
fi

# --------------------------------------------------------------------------
# 2. Create conda environments
# --------------------------------------------------------------------------
echo "[1/3] Creating conda environments..."

FAIL=0

create_env() {
    local name=$1; shift
    if mamba env list 2>/dev/null | grep -qE "^${name}\s"; then
        echo "  SKIP  ${name} (already exists)"
        return 0
    fi
    echo -n "  ...   ${name}"
    if "$@" > /tmp/radar_install_${name}.log 2>&1; then
        echo -e "\r  OK    ${name}"
    else
        echo -e "\r  FAIL  ${name} (see /tmp/radar_install_${name}.log)"
        FAIL=1
        return 1
    fi
}

echo ""
echo "  --- Base environment (radar) ---"
if ! mamba env list 2>/dev/null | grep -qE "^radar\s"; then
    echo -n "  ...   radar"
    if mamba create -n radar -y -c bioconda -c conda-forge \
        "python>=3.11,<3.13" \
        fastp filtlong flye spades polypolish bwa \
        hmmer blast quast \
        mlst skani minced prodigal \
        sistr_cmd kleborate \
        sra-tools viennarna infernal \
        > /tmp/radar_install_radar.log 2>&1; then
        echo -e "\r  OK    radar"
    else
        echo -e "\r  FAIL  radar (see /tmp/radar_install_radar.log)"
        FAIL=1
    fi
else
    echo "  SKIP  radar (already exists)"
fi

# Install pip packages into base radar env
echo ""
echo "  --- Pip packages in base env ---"

pip_install_one() {
    local label=$1; shift
    echo -n "  ...   ${label}"
    if conda run -n radar pip install --quiet "$@" >> /tmp/radar_install_radar_pip.log 2>&1; then
        echo -e "\r  OK    ${label}"
    else
        echo -e "\r  FAIL  ${label} (see /tmp/radar_install_radar_pip.log)"
        FAIL=1
    fi
}

: > /tmp/radar_install_radar_pip.log
pip_install_one "defense-finder" mdmparis-defense-finder
pip_install_one "integron_finder" integron_finder
pip_install_one "chewbbaca" chewbbaca
pip_install_one "resfinder" resfinder
pip_install_one "OSTIR" OSTIR

# AMRFinderPlus: install binaries from GitHub release into base env
echo ""
echo "  --- AMRFinderPlus binaries ---"
AMRFINDER_BIN="$(conda run -n radar bash -c 'echo $CONDA_PREFIX/bin')"
if [ -x "${AMRFINDER_BIN}/amrfinder" ]; then
    echo "  SKIP  AMRFinderPlus (already installed)"
else
    echo -n "  ...   AMRFinderPlus"
    if curl -sL "https://github.com/ncbi/amr/releases/download/amrfinder_v4.2.7/amrfinder_binaries_v4.2.7.tar.gz" -o /tmp/amrfinder_bin.tar.gz \
        && mkdir -p /tmp/amrfinder_extract \
        && tar xzf /tmp/amrfinder_bin.tar.gz -C /tmp/amrfinder_extract \
        && cp /tmp/amrfinder_extract/amrfinder /tmp/amrfinder_extract/amrfinder_update /tmp/amrfinder_extract/amrfinder_index \
              /tmp/amrfinder_extract/amr_report /tmp/amrfinder_extract/fasta_check /tmp/amrfinder_extract/fasta2parts \
              /tmp/amrfinder_extract/fasta_extract /tmp/amrfinder_extract/gff_check /tmp/amrfinder_extract/dna_mutation \
              "$AMRFINDER_BIN/" 2>/dev/null \
        && chmod +x "$AMRFINDER_BIN"/amrfinder* "$AMRFINDER_BIN"/fasta_check "$AMRFINDER_BIN"/amr_report \
                    "$AMRFINDER_BIN"/fasta2parts "$AMRFINDER_BIN"/fasta_extract "$AMRFINDER_BIN"/gff_check \
                    "$AMRFINDER_BIN"/dna_mutation 2>/dev/null \
        && rm -rf /tmp/amrfinder_bin.tar.gz /tmp/amrfinder_extract; then
        echo -e "\r  OK    AMRFinderPlus"
    else
        echo -e "\r  FAIL  AMRFinderPlus"
        FAIL=1
    fi
fi

echo ""
echo "  --- Separate environments (conflicting deps) ---"

# mob_suite needs python<=3.11
if ! mamba env list 2>/dev/null | grep -qE "^radar-mobsuite\s"; then
    echo -n "  ...   radar-mobsuite"
    if mamba create -n radar-mobsuite -y python=3.11 -c conda-forge > /tmp/radar_install_radar-mobsuite.log 2>&1 \
        && conda run -n radar-mobsuite pip install --quiet mob_suite >> /tmp/radar_install_radar-mobsuite.log 2>&1; then
        echo -e "\r  OK    radar-mobsuite"
    else
        echo -e "\r  FAIL  radar-mobsuite (see /tmp/radar_install_radar-mobsuite.log)"
        FAIL=1
    fi
else
    echo "  SKIP  radar-mobsuite (already exists)"
fi

# MobileElementFinder needs setuptools<81 and python<=3.11
if ! mamba env list 2>/dev/null | grep -qE "^radar-mefinder\s"; then
    echo -n "  ...   radar-mefinder"
    if mamba create -n radar-mefinder -y python=3.11 -c conda-forge > /tmp/radar_install_radar-mefinder.log 2>&1 \
        && conda run -n radar-mefinder pip install --quiet "setuptools<81" MobileElementFinder >> /tmp/radar_install_radar-mefinder.log 2>&1; then
        echo -e "\r  OK    radar-mefinder"
    else
        echo -e "\r  FAIL  radar-mefinder (see /tmp/radar_install_radar-mefinder.log)"
        FAIL=1
    fi
else
    echo "  SKIP  radar-mefinder (already exists)"
fi

# medaka has strict htslib constraints — needs python=3.10
# Install CPU-only PyTorch first to avoid pulling ~3GB of CUDA/GPU libs
if ! mamba env list 2>/dev/null | grep -qE "^radar-medaka\s"; then
    echo -n "  ...   radar-medaka"
    if mamba create -n radar-medaka -y python=3.10 -c conda-forge > /tmp/radar_install_radar-medaka.log 2>&1 \
        && conda run -n radar-medaka pip install --quiet \
            torch --extra-index-url https://download.pytorch.org/whl/cpu \
            >> /tmp/radar_install_radar-medaka.log 2>&1 \
        && conda run -n radar-medaka pip install --quiet --no-deps medaka >> /tmp/radar_install_radar-medaka.log 2>&1 \
        && conda run -n radar-medaka pip install --quiet medaka >> /tmp/radar_install_radar-medaka.log 2>&1; then
        echo -e "\r  OK    radar-medaka"
    else
        echo -e "\r  FAIL  radar-medaka (see /tmp/radar_install_radar-medaka.log)"
        FAIL=1
    fi
else
    echo "  SKIP  radar-medaka (already exists)"
fi

# geNomad needs python=3.10
# Install tensorflow-cpu first to avoid pulling ~1.5GB of GPU tensorflow
if ! mamba env list 2>/dev/null | grep -qE "^radar-genomad\s"; then
    echo -n "  ...   radar-genomad"
    if mamba create -n radar-genomad -y python=3.10 -c conda-forge > /tmp/radar_install_radar-genomad.log 2>&1 \
        && conda run -n radar-genomad pip install --quiet tensorflow-cpu >> /tmp/radar_install_radar-genomad.log 2>&1 \
        && conda run -n radar-genomad pip install --quiet genomad >> /tmp/radar_install_radar-genomad.log 2>&1; then
        echo -e "\r  OK    radar-genomad"
    else
        echo -e "\r  FAIL  radar-genomad (see /tmp/radar_install_radar-genomad.log)"
        FAIL=1
    fi
else
    echo "  SKIP  radar-genomad (already exists)"
fi

# BUSCO: complex deps (hmmer, prodigal, bbmap + pip from gitlab)
if ! mamba env list 2>/dev/null | grep -qE "^radar-busco\s"; then
    echo -n "  ...   radar-busco"
    if mamba create -n radar-busco -y python=3.10 hmmer prodigal bbmap -c bioconda -c conda-forge > /tmp/radar_install_radar-busco.log 2>&1 \
        && conda run -n radar-busco pip install --quiet "git+https://gitlab.com/ezlab/busco.git" pandas biopython requests >> /tmp/radar_install_radar-busco.log 2>&1; then
        echo -e "\r  OK    radar-busco"
    else
        echo -e "\r  FAIL  radar-busco (see /tmp/radar_install_radar-busco.log)"
        FAIL=1
    fi
else
    echo "  SKIP  radar-busco (already exists)"
fi

echo ""
if [ "${FAIL}" -eq 1 ]; then
    echo "WARNING: Some environments failed. Check /tmp/radar_install_*.log"
    echo "Re-run this script to retry failed envs (existing ones are skipped)."
    echo ""
fi

# --------------------------------------------------------------------------
# 3. Download databases (skip with -e flag)
# --------------------------------------------------------------------------
if [ "${ENVS_ONLY}" -eq 1 ]; then
    echo "[2/3] Skipping database downloads (-e flag)"
    echo ""
    echo "[3/3] Skipping optional tools (-e flag)"
    echo ""
    echo "============================================"
    echo "  RADAR install complete (envs only)!"
    echo "============================================"
    exit 0
fi

echo "[2/3] Downloading databases..."
mkdir -p "${DB_DIR}"

# AMRFinderPlus database
echo -n "  AMRFinderPlus database..."
AMRFINDER_DB_DIR="${DB_DIR}/amrfinderplus"
if [ -d "${AMRFINDER_DB_DIR}" ] && [ -f "${AMRFINDER_DB_DIR}/AMRProt" ]; then
    echo " exists"
else
    AMRFINDER_BIN_DIR="$(conda run -n radar bash -c 'echo ${CONDA_PREFIX}/bin')"
    if conda run -n radar amrfinder --update > /tmp/radar_db_amrfinder.log 2>&1; then
        ln -sfn "${AMRFINDER_BIN_DIR}/data/latest" "${AMRFINDER_DB_DIR}" 2>/dev/null
        echo " done"
    else
        echo ""
        echo "    amrfinder --update failed; downloading manually..."
        AMRFINDER_FTP="https://ftp.ncbi.nlm.nih.gov/pathogen/Antimicrobial_resistance/AMRFinderPlus/database/latest"
        mkdir -p "${AMRFINDER_DB_DIR}"
        FILE_LIST=$(curl -sL "${AMRFINDER_FTP}/" | grep -oP 'href="([^"/]+)"' | sed 's/href="//;s/"//' | grep -v '/$')
        for f in $FILE_LIST; do
            curl -sfL "${AMRFINDER_FTP}/${f}" -o "${AMRFINDER_DB_DIR}/${f}" 2>/dev/null || true
        done
        if [ -f "${AMRFINDER_DB_DIR}/AMRProt.fa" ]; then
            conda run -n radar makeblastdb -in "${AMRFINDER_DB_DIR}/AMRProt.fa" -dbtype prot -out "${AMRFINDER_DB_DIR}/AMRProt.fa" >> /tmp/radar_db_amrfinder.log 2>&1 || true
            conda run -n radar makeblastdb -in "${AMRFINDER_DB_DIR}/AMR_CDS.fa" -dbtype nucl -out "${AMRFINDER_DB_DIR}/AMR_CDS.fa" >> /tmp/radar_db_amrfinder.log 2>&1 || true
            for dna_fa in "${AMRFINDER_DB_DIR}"/AMR_DNA-*.fa; do
                [ -f "$dna_fa" ] && conda run -n radar makeblastdb -in "$dna_fa" -dbtype nucl -out "$dna_fa" >> /tmp/radar_db_amrfinder.log 2>&1 || true
            done
            [ -f "${AMRFINDER_DB_DIR}/amr_targets.fa" ] && conda run -n radar makeblastdb -in "${AMRFINDER_DB_DIR}/amr_targets.fa" -dbtype nucl -out "${AMRFINDER_DB_DIR}/amr_targets.fa" >> /tmp/radar_db_amrfinder.log 2>&1 || true
            conda run -n radar hmmpress -f "${AMRFINDER_DB_DIR}/AMR.LIB" >> /tmp/radar_db_amrfinder.log 2>&1 || true
        fi
        if [ -f "${AMRFINDER_DB_DIR}/AMRProt.fa" ]; then
            mkdir -p "${AMRFINDER_BIN_DIR}/data"
            ln -sfn "${AMRFINDER_DB_DIR}" "${AMRFINDER_BIN_DIR}/data/latest" 2>/dev/null
            echo "    done (manual download)"
        else
            echo "    FAILED"
        fi
    fi
fi

# geNomad database (~3.5 GB)
echo -n "  geNomad database..."
if [ -d "${DB_DIR}/genomad_db" ]; then
    echo " exists"
else
    if conda run -n radar-genomad genomad download-database "${DB_DIR}" > /tmp/radar_db_genomad.log 2>&1; then
        echo " done"
    else
        echo " FAILED (see /tmp/radar_db_genomad.log)"
    fi
fi

# skani GTDB sketch database (~30 GB compressed, ~50 GB uncompressed)
# Skipped by default — too large for auto-download. 16S BLAST is used as fallback.
# To install manually:
#   mkdir -p ${DB_DIR}/skani
#   curl -L -o ${DB_DIR}/skani/skani_gtdb_r226-v0.3.tar.gz http://faust.compbio.cs.cmu.edu/skani-files/skani_gtdb_r226-v0.3.tar.gz
#   tar xzf ${DB_DIR}/skani/skani_gtdb_r226-v0.3.tar.gz -C ${DB_DIR}/skani && rm ${DB_DIR}/skani/skani_gtdb_r226-v0.3.tar.gz
echo "  skani GTDB database... skipped (30 GB, optional — see install.sh for manual instructions)"

# NCBI 16S rRNA BLAST database
echo -n "  16S rRNA BLAST database..."
if [ -f "${DB_DIR}/16S/16S_ribosomal_RNA.ndb" ]; then
    echo " exists"
else
    mkdir -p "${DB_DIR}/16S"
    if (cd "${DB_DIR}/16S" && \
        curl -sL -O "https://ftp.ncbi.nlm.nih.gov/blast/db/16S_ribosomal_RNA.tar.gz" \
        && tar xzf 16S_ribosomal_RNA.tar.gz \
        && rm 16S_ribosomal_RNA.tar.gz); then
        echo " done"
    else
        echo " FAILED"
    fi
fi

# MOB-suite database
echo -n "  MOB-suite database..."
if conda run -n radar mob_init > /tmp/radar_db_mobsuite.log 2>&1; then
    echo " done"
else
    echo " FAILED (will auto-download on first run)"
fi

# PointFinder database
echo -n "  PointFinder database..."
if [ -d "${DB_DIR}/pointfinder_db" ]; then
    echo " exists"
else
    if git clone --quiet https://bitbucket.org/genomicepidemiology/pointfinder_db.git "${DB_DIR}/pointfinder_db" 2>/dev/null; then
        echo " done"
    else
        echo " FAILED"
    fi
fi

# ResFinder database
echo -n "  ResFinder database..."
if [ -d "${DB_DIR}/resfinder_db" ]; then
    echo " exists"
else
    if git clone --quiet https://bitbucket.org/genomicepidemiology/resfinder_db.git "${DB_DIR}/resfinder_db" 2>/dev/null; then
        echo " done"
    else
        echo " FAILED"
    fi
fi

# Rfam CM database (for sRNA annotation via cmscan)
echo -n "  Rfam database..."
if [ -f "${DB_DIR}/Rfam.cm" ]; then
    echo " exists"
else
    if curl -sL -o "${DB_DIR}/Rfam.cm.gz" "https://ftp.ebi.ac.uk/pub/databases/Rfam/CURRENT/Rfam.cm.gz" \
        && gunzip "${DB_DIR}/Rfam.cm.gz" \
        && conda run -n radar cmpress "${DB_DIR}/Rfam.cm" > /dev/null 2>&1; then
        echo " done"
    else
        echo " FAILED"
    fi
fi

# DefenseFinder models
echo -n "  DefenseFinder models..."
if conda run -n radar defense-finder update > /tmp/radar_db_defense.log 2>&1; then
    echo " done"
else
    echo " FAILED (see /tmp/radar_db_defense.log)"
fi

# --------------------------------------------------------------------------
# 4. BPROM binary (optional)
# --------------------------------------------------------------------------
echo ""
echo "[3/3] Checking optional tools..."

BPROM_BIN=""
if [ -d /tmp/bprom ] || [ -f /tmp/bprom ]; then
    BPROM_BIN="$(conda run --no-banner -n radar bash -c 'dirname $(which prodigal)' 2>/dev/null)" || true
fi

if [ -d /tmp/bprom ] && [ -n "$BPROM_BIN" ]; then
    cp /tmp/bprom/linux/bprom "${BPROM_BIN}/bprom" 2>/dev/null && chmod +x "${BPROM_BIN}/bprom" || true
    cp /tmp/bprom/bprom_data/* "${BPROM_BIN}/" 2>/dev/null || true
    echo "  BPROM installed"
elif [ -f /tmp/bprom ] && [ -n "$BPROM_BIN" ]; then
    cp /tmp/bprom "${BPROM_BIN}/bprom" 2>/dev/null && chmod +x "${BPROM_BIN}/bprom" || true
    echo "  BPROM binary installed (data files may be missing)"
else
    echo "  BPROM not found at /tmp/bprom — skipping (optional)"
fi

# --------------------------------------------------------------------------
# Done
# --------------------------------------------------------------------------
echo ""
echo "============================================"
echo "  RADAR install complete!"
echo "============================================"
echo ""
echo "  Databases: ${DB_DIR}"
echo ""
echo "  Conda environments installed:"
echo "    Base:     radar (fastp, filtlong, flye, spades, polypolish, bwa,"
echo "              hmmer, blast, quast, mlst, skani, minced, prodigal,"
echo "              sistr_cmd, kleborate, sra-tools, viennarna, infernal,"
echo "              defense-finder, integron_finder, chewbbaca, resfinder,"
echo "              OSTIR, AMRFinderPlus)"
echo "    Separate: radar-mobsuite, radar-mefinder, radar-medaka,"
echo "              radar-genomad, radar-busco"
echo ""
echo "  Run the pipeline:"
echo "    ./pipeline.sh -1 sample_R1.fastq.gz -2 sample_R2.fastq.gz -o results/"
echo ""
