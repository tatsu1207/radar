#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# RADAR - Install Script
# ============================================================================
# Installs all bioinformatics tools (one tool per conda env) and databases.
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
# 2. Create conda environments (one tool per env, sequential to avoid lock)
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

# Helper for envs that need pip install after mamba create
create_env_pip() {
    local name=$1
    local pip_pkg=$2
    shift 2
    if mamba env list 2>/dev/null | grep -qE "^${name}\s"; then
        echo "  SKIP  ${name} (already exists)"
        return 0
    fi
    echo -n "  ...   ${name}"
    if "$@" > /tmp/radar_install_${name}.log 2>&1 \
        && conda run -n "${name}" pip install --quiet "${pip_pkg}" >> /tmp/radar_install_${name}.log 2>&1; then
        echo -e "\r  OK    ${name}"
    else
        echo -e "\r  FAIL  ${name} (see /tmp/radar_install_${name}.log)"
        FAIL=1
        return 1
    fi
}

echo ""
echo "  --- QC ---"
create_env radar-fastp \
    mamba create -n radar-fastp -y -c bioconda -c conda-forge fastp || true
create_env radar-filtlong \
    mamba create -n radar-filtlong -y -c bioconda -c conda-forge filtlong || true

echo "  --- Assembly ---"
create_env radar-spades \
    mamba create -n radar-spades -y -c bioconda -c conda-forge spades || true
create_env radar-flye \
    mamba create -n radar-flye -y -c bioconda -c conda-forge flye || true
# medaka has strict htslib constraints — pin python and install via pip
create_env_pip radar-medaka medaka \
    mamba create -n radar-medaka -y python=3.10 -c conda-forge || true
create_env radar-polypolish \
    mamba create -n radar-polypolish -y -c bioconda -c conda-forge polypolish bwa || true

echo "  --- Assembly QC ---"
create_env radar-quast \
    mamba create -n radar-quast -y -c bioconda -c conda-forge quast || true

# BUSCO: mamba env + pip install from gitlab
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

echo "  --- Annotation ---"
# AMRFinderPlus: create env with deps, then install binaries from GitHub release
if ! mamba env list 2>/dev/null | grep -qE "^radar-amrfinder\s"; then
    echo -n "  ...   radar-amrfinder"
    if mamba create -n radar-amrfinder -y python=3.11 hmmer blast -c bioconda -c conda-forge > /tmp/radar_install_radar-amrfinder.log 2>&1; then
        AMRFINDER_BIN="$(conda run -n radar-amrfinder bash -c 'echo $CONDA_PREFIX/bin')"
        curl -sL "https://github.com/ncbi/amr/releases/download/amrfinder_v4.2.7/amrfinder_binaries_v4.2.7.tar.gz" -o /tmp/amrfinder_bin.tar.gz \
            && mkdir -p /tmp/amrfinder_extract \
            && tar xzf /tmp/amrfinder_bin.tar.gz -C /tmp/amrfinder_extract \
            && cp /tmp/amrfinder_extract/amrfinder /tmp/amrfinder_extract/amrfinder_update /tmp/amrfinder_extract/amrfinder_index \
                  /tmp/amrfinder_extract/amr_report /tmp/amrfinder_extract/fasta_check /tmp/amrfinder_extract/fasta2parts \
                  /tmp/amrfinder_extract/fasta_extract /tmp/amrfinder_extract/gff_check /tmp/amrfinder_extract/dna_mutation \
                  "$AMRFINDER_BIN/" 2>/dev/null \
            && chmod +x "$AMRFINDER_BIN"/amrfinder* "$AMRFINDER_BIN"/fasta_check "$AMRFINDER_BIN"/amr_report \
                        "$AMRFINDER_BIN"/fasta2parts "$AMRFINDER_BIN"/fasta_extract "$AMRFINDER_BIN"/gff_check \
                        "$AMRFINDER_BIN"/dna_mutation 2>/dev/null \
            && rm -rf /tmp/amrfinder_bin.tar.gz /tmp/amrfinder_extract \
            >> /tmp/radar_install_radar-amrfinder.log 2>&1
        echo -e "\r  OK    radar-amrfinder"
    else
        echo -e "\r  FAIL  radar-amrfinder (see /tmp/radar_install_radar-amrfinder.log)"
        FAIL=1
    fi
else
    echo "  SKIP  radar-amrfinder (already exists)"
fi

create_env_pip radar-mobsuite mob_suite \
    mamba create -n radar-mobsuite -y python=3.11 -c conda-forge || true

# MobileElementFinder needs setuptools for pkg_resources
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

# mlst needs perl>=5.32
create_env radar-mlst \
    mamba create -n radar-mlst -y -c bioconda -c conda-forge mlst "perl>=5.32" || true

create_env radar-skani \
    mamba create -n radar-skani -y -c bioconda -c conda-forge skani || true

# integron_finder has biopython conflicts — install via pip
create_env_pip radar-integron integron_finder \
    mamba create -n radar-integron -y python=3.11 hmmer infernal -c bioconda -c conda-forge || true

create_env_pip radar-genomad genomad \
    mamba create -n radar-genomad -y python=3.10 -c conda-forge || true

create_env radar-serotype \
    mamba create -n radar-serotype -y -c bioconda -c conda-forge sistr_cmd kleborate || true

# chewBBACA has complex deps — install via pip with blast from conda
create_env_pip radar-cgmlst chewbbaca \
    mamba create -n radar-cgmlst -y python=3.11 blast -c bioconda -c conda-forge || true

# CRISPRCasFinder: package name is ccfinder in bioconda, or use minced as lighter alternative
create_env radar-crispr \
    mamba create -n radar-crispr -y -c bioconda -c conda-forge minced || true

create_env_pip radar-defense mdmparis-defense-finder \
    mamba create -n radar-defense -y python=3.11 -c conda-forge || true

create_env radar-blast \
    mamba create -n radar-blast -y -c bioconda -c conda-forge blast || true

create_env radar-prodigal \
    mamba create -n radar-prodigal -y -c bioconda -c conda-forge prodigal || true

# OSTIR needs ViennaRNA
create_env_pip radar-ostir OSTIR \
    mamba create -n radar-ostir -y python=3.11 viennarna -c bioconda -c conda-forge || true

create_env_pip radar-resfinder resfinder \
    mamba create -n radar-resfinder -y python=3.11 -c conda-forge || true

echo "  --- Utilities ---"
create_env radar-sra \
    mamba create -n radar-sra -y -c bioconda -c conda-forge sra-tools || true

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
    # Try amrfinder --update first; fall back to manual FTP download
    AMRFINDER_BIN_DIR="$(conda run -n radar-amrfinder bash -c 'echo ${CONDA_PREFIX}/bin')"
    if conda run -n radar-amrfinder amrfinder --update > /tmp/radar_db_amrfinder.log 2>&1; then
        # Symlink the default location
        ln -sfn "${AMRFINDER_BIN_DIR}/data/latest" "${AMRFINDER_DB_DIR}" 2>/dev/null
        echo " done"
    else
        # Manual download from NCBI FTP
        echo ""
        echo "    amrfinder --update failed; downloading manually..."
        AMRFINDER_FTP="https://ftp.ncbi.nlm.nih.gov/pathogen/Antimicrobial_resistance/AMRFinderPlus/database/latest"
        mkdir -p "${AMRFINDER_DB_DIR}"
        # Get file list from FTP index and download all files
        FILE_LIST=$(curl -sL "${AMRFINDER_FTP}/" | grep -oP 'href="([^"/]+)"' | sed 's/href="//;s/"//' | grep -v '/$')
        for f in $FILE_LIST; do
            curl -sfL "${AMRFINDER_FTP}/${f}" -o "${AMRFINDER_DB_DIR}/${f}" 2>/dev/null || true
        done
        # Build BLAST indexes
        if [ -f "${AMRFINDER_DB_DIR}/AMRProt.fa" ]; then
            conda run -n radar-amrfinder makeblastdb -in "${AMRFINDER_DB_DIR}/AMRProt.fa" -dbtype prot -out "${AMRFINDER_DB_DIR}/AMRProt.fa" >> /tmp/radar_db_amrfinder.log 2>&1 || true
            conda run -n radar-amrfinder makeblastdb -in "${AMRFINDER_DB_DIR}/AMR_CDS.fa" -dbtype nucl -out "${AMRFINDER_DB_DIR}/AMR_CDS.fa" >> /tmp/radar_db_amrfinder.log 2>&1 || true
            for dna_fa in "${AMRFINDER_DB_DIR}"/AMR_DNA-*.fa; do
                [ -f "$dna_fa" ] && conda run -n radar-amrfinder makeblastdb -in "$dna_fa" -dbtype nucl -out "$dna_fa" >> /tmp/radar_db_amrfinder.log 2>&1 || true
            done
            [ -f "${AMRFINDER_DB_DIR}/amr_targets.fa" ] && conda run -n radar-amrfinder makeblastdb -in "${AMRFINDER_DB_DIR}/amr_targets.fa" -dbtype nucl -out "${AMRFINDER_DB_DIR}/amr_targets.fa" >> /tmp/radar_db_amrfinder.log 2>&1 || true
            conda run -n radar-amrfinder hmmpress -f "${AMRFINDER_DB_DIR}/AMR.LIB" >> /tmp/radar_db_amrfinder.log 2>&1 || true
        fi
        if [ -f "${AMRFINDER_DB_DIR}/AMRProt.fa" ]; then
            # Symlink so amrfinder can find it
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

# skani GTDB sketch database (~1.5 GB)
echo -n "  skani GTDB database..."
if [ -d "${DB_DIR}/skani" ]; then
    echo " exists"
else
    mkdir -p "${DB_DIR}/skani"
    if curl -sL -o "${DB_DIR}/skani/skani-gtdb.tar.gz" \
        "https://zenodo.org/records/10890155/files/skani-gtdb-r220-sketch.tar.gz" \
        && tar xzf "${DB_DIR}/skani/skani-gtdb.tar.gz" -C "${DB_DIR}/skani" \
        && rm "${DB_DIR}/skani/skani-gtdb.tar.gz"; then
        echo " done"
    else
        echo " FAILED"
    fi
fi

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
if conda run -n radar-mobsuite mob_init > /tmp/radar_db_mobsuite.log 2>&1; then
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
        && conda run -n radar-blast cmpress "${DB_DIR}/Rfam.cm" > /dev/null 2>&1; then
        echo " done"
    else
        echo " FAILED"
    fi
fi

# DefenseFinder models
echo -n "  DefenseFinder models..."
if conda run -n radar-defense defense-finder update > /tmp/radar_db_defense.log 2>&1; then
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
    BPROM_BIN="$(conda run --no-banner -n radar-prodigal bash -c 'dirname $(which prodigal)' 2>/dev/null)" || true
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
echo "    QC:         radar-fastp, radar-filtlong"
echo "    Assembly:   radar-spades, radar-flye, radar-medaka, radar-polypolish"
echo "    AssemblyQC: radar-quast, radar-busco"
echo "    Annotation: radar-amrfinder, radar-mobsuite, radar-mefinder,"
echo "                radar-mlst, radar-skani, radar-integron, radar-genomad,"
echo "                radar-serotype, radar-cgmlst, radar-crispr, radar-defense,"
echo "                radar-blast, radar-prodigal, radar-ostir, radar-resfinder"
echo "    Utilities:  radar-sra"
echo ""
echo "  Run the pipeline:"
echo "    ./pipeline.sh -1 sample_R1.fastq.gz -2 sample_R2.fastq.gz -o results/"
echo ""
