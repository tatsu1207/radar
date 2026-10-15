#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# RADAR - Install Script
# ============================================================================
# Installs bioinformatics tools: one base `radar` env plus separate envs only
# for tools with incompatible dependencies.
# Requires: mamba (Miniforge)
# Usage: ./install.sh
#
# After installation, run ./databases/download_dbs.sh to download databases.
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================"
echo "  RADAR Install (tools only)"
echo "============================================"
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
echo "[1/2] Creating conda environments..."

FAIL=0

echo ""
echo "  --- Base environment (radar) ---"
if ! conda env list 2>/dev/null | grep -qE "^radar\s"; then
    echo -n "  ...   radar"
    if mamba create -n radar -y -c bioconda -c conda-forge \
        "python>=3.11,<3.13" \
        fastp chopper flye spades polypolish bwa \
        hmmer blast \
        mlst skani minced prodigal \
        sra-tools viennarna infernal \
        postgresql redis-server \
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
# Backend web-app dependencies (FastAPI, Celery, SQLAlchemy, scikit-learn, ...).
# Installed before defense-finder, which pins click==8.0.3 (celery asks for >=8.1.2 but runs with 8.0.3).
echo -n "  ...   backend requirements"
if conda run -n radar pip install --quiet -r "${SCRIPT_DIR}/backend/requirements.txt" >> /tmp/radar_install_radar_pip.log 2>&1; then
    echo -e "\r  OK    backend requirements"
else
    echo -e "\r  FAIL  backend requirements (see /tmp/radar_install_radar_pip.log)"
    FAIL=1
fi

pip_install_one "defense-finder" mdmparis-defense-finder "click==8.0.3"
pip_install_one "integron_finder" integron_finder
pip_install_one "chewbbaca" chewbbaca
pip_install_one "resfinder" resfinder

# Frontend: Node.js >= 18.17 (Next.js 14) and npm packages.
# A node already on PATH (e.g. nvm) is used if new enough; otherwise nodejs is added to the radar env.
echo ""
echo "  --- Frontend (Node.js + npm packages) ---"
node_ok() {
    conda run -n radar node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit(a>18||(a==18&&b>=17)?0:1)' >/dev/null 2>&1
}
if node_ok; then
    echo "  SKIP  nodejs ($(conda run -n radar node -v 2>/dev/null) already available)"
else
    echo -n "  ...   nodejs"
    if mamba install -n radar -y -c conda-forge "nodejs>=18.17,<23" > /tmp/radar_install_nodejs.log 2>&1 && node_ok; then
        echo -e "\r  OK    nodejs"
    else
        echo -e "\r  FAIL  nodejs (see /tmp/radar_install_nodejs.log)"
        FAIL=1
    fi
fi
echo -n "  ...   npm packages"
if (cd "${SCRIPT_DIR}/frontend" && conda run -n radar npm ci --no-audit --no-fund) > /tmp/radar_install_npm.log 2>&1; then
    echo -e "\r  OK    npm packages"
else
    echo -e "\r  FAIL  npm packages (see /tmp/radar_install_npm.log)"
    FAIL=1
fi

# sistr_cmd + kleborate + serotypefinder: need separate env due to pytables/hdf5/libcurl conflicts
echo ""
echo "  --- sistr_cmd + kleborate + serotypefinder environment ---"
if ! conda env list 2>/dev/null | grep -qE "^radar-sistr\s"; then
    echo -n "  ...   radar-sistr"
    if mamba create -n radar-sistr -y python=3.10 sistr_cmd kleborate serotypefinder -c bioconda -c conda-forge --channel-priority flexible > /tmp/radar_install_radar-sistr.log 2>&1 \
        && conda run -n radar-sistr pip install --quiet "setuptools<81" >> /tmp/radar_install_radar-sistr.log 2>&1; then
        echo -e "\r  OK    radar-sistr"
    else
        echo -e "\r  FAIL  radar-sistr (see /tmp/radar_install_radar-sistr.log)"
        FAIL=1
    fi
else
    echo "  SKIP  radar-sistr (already exists)"
fi

# quast: has complex boost/blast/simplejson conflicts with python>=3.11
if ! conda env list 2>/dev/null | grep -qE "^radar-quast\s"; then
    echo -n "  ...   radar-quast"
    if mamba create -n radar-quast -y python=3.10 quast -c bioconda -c conda-forge --channel-priority flexible > /tmp/radar_install_radar-quast.log 2>&1; then
        echo -e "\r  OK    radar-quast"
    else
        echo -e "\r  FAIL  radar-quast (see /tmp/radar_install_radar-quast.log)"
        FAIL=1
    fi
else
    echo "  SKIP  radar-quast (already exists)"
fi

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
if ! conda env list 2>/dev/null | grep -qE "^radar-mobsuite\s"; then
    echo -n "  ...   radar-mobsuite"
    if mamba create -n radar-mobsuite -y python=3.11 blast mash -c conda-forge -c bioconda > /tmp/radar_install_radar-mobsuite.log 2>&1 \
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
if ! conda env list 2>/dev/null | grep -qE "^radar-mefinder\s"; then
    echo -n "  ...   radar-mefinder"
    if mamba create -n radar-mefinder -y python=3.11 blast -c conda-forge -c bioconda > /tmp/radar_install_radar-mefinder.log 2>&1 \
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
if ! conda env list 2>/dev/null | grep -qE "^radar-medaka\s"; then
    echo -n "  ...   radar-medaka"
    if mamba create -n radar-medaka -y python=3.10 -c conda-forge > /tmp/radar_install_radar-medaka.log 2>&1 \
        && conda run -n radar-medaka pip install --quiet \
            torch --extra-index-url https://download.pytorch.org/whl/cpu \
            >> /tmp/radar_install_radar-medaka.log 2>&1 \
        && conda run -n radar-medaka pip install --quiet --no-deps medaka >> /tmp/radar_install_radar-medaka.log 2>&1 \
        && conda run -n radar-medaka pip install --quiet medaka >> /tmp/radar_install_radar-medaka.log 2>&1 \
        && mamba install -n radar-medaka -y -c bioconda -c conda-forge minimap2 >> /tmp/radar_install_radar-medaka.log 2>&1; then
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
if ! conda env list 2>/dev/null | grep -qE "^radar-genomad\s"; then
    echo -n "  ...   radar-genomad"
    if mamba create -n radar-genomad -y python=3.10 mmseqs2 aragorn -c conda-forge -c bioconda > /tmp/radar_install_radar-genomad.log 2>&1 \
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

# Plassembler: small-plasmid recovery after Flye (Flye misses plasmids < ~20 kb).
# Pins its own flye/unicycler/dnaapler versions, so it gets a separate env.
if ! conda env list 2>/dev/null | grep -qE "^radar-plassembler\s"; then
    echo -n "  ...   radar-plassembler"
    if mamba create -n radar-plassembler -y -c conda-forge -c bioconda "plassembler=1.8.5" > /tmp/radar_install_radar-plassembler.log 2>&1; then
        echo -e "\r  OK    radar-plassembler"
    else
        echo -e "\r  FAIL  radar-plassembler (see /tmp/radar_install_radar-plassembler.log)"
        FAIL=1
    fi
else
    echo "  SKIP  radar-plassembler (already exists)"
fi

# OSTIR: RBS analysis. Needs ViennaRNA >= 2.6 Python bindings for py3.11; in the base env
# that upgrade would remove mlst (old perl), so OSTIR gets its own env.
if ! conda env list 2>/dev/null | grep -qE "^radar-ostir\s"; then
    echo -n "  ...   radar-ostir"
    if mamba create -n radar-ostir -y -c conda-forge -c bioconda python=3.11 "viennarna>=2.6" > /tmp/radar_install_radar-ostir.log 2>&1 \
        && conda run -n radar-ostir pip install --quiet "ostir==1.1.3" >> /tmp/radar_install_radar-ostir.log 2>&1 \
        && conda run -n radar-ostir python -c "import RNA, ostir" >> /tmp/radar_install_radar-ostir.log 2>&1; then
        echo -e "\r  OK    radar-ostir"
    else
        echo -e "\r  FAIL  radar-ostir (see /tmp/radar_install_radar-ostir.log)"
        FAIL=1
    fi
else
    echo "  SKIP  radar-ostir (already exists)"
fi

# BUSCO: complex deps (hmmer, prodigal, bbmap + pip from gitlab)
if ! conda env list 2>/dev/null | grep -qE "^radar-busco\s"; then
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

# --------------------------------------------------------------------------
# 3. BPROM binary (optional)
# --------------------------------------------------------------------------
echo ""
echo "[2/2] Checking optional tools..."

# BPROM (promoter prediction) ships in bin/ (32-bit i386 binary + data files). It is copied into
# the radar env's bin/, where the pipeline finds the binary on PATH and the data via TSS_DATA.
BPROM_BIN="$(conda run -n radar bash -c 'echo $CONDA_PREFIX/bin' 2>/dev/null)" || true
BPROM_SRC="${SCRIPT_DIR}/bin"
[ -d /tmp/bprom/linux ] && BPROM_SRC=/tmp/bprom/linux  # optional override with a newer copy
if [ -n "$BPROM_BIN" ] && [ -f "${BPROM_SRC}/bprom" ]; then
    cp "${BPROM_SRC}/bprom" "${BPROM_BIN}/bprom" && chmod +x "${BPROM_BIN}/bprom"
    cp "${SCRIPT_DIR}/bin/bprom_data/"* "${BPROM_BIN}/" 2>/dev/null || true
    [ -d /tmp/bprom/bprom_data ] && cp /tmp/bprom/bprom_data/* "${BPROM_BIN}/" 2>/dev/null || true
    if [ -e /lib/ld-linux.so.2 ]; then
        echo "  OK    BPROM"
    else
        echo "  WARN  BPROM installed, but it is a 32-bit binary and the 32-bit loader is missing."
        echo "        Install it to enable promoter prediction, e.g. Debian/Ubuntu:"
        echo "          sudo dpkg --add-architecture i386 && sudo apt update && sudo apt install libc6:i386"
    fi
else
    echo "  SKIP  BPROM (bin/bprom not found; promoter prediction disabled)"
fi

# --------------------------------------------------------------------------
# Done
# --------------------------------------------------------------------------
echo ""
if [ "${FAIL}" -eq 1 ]; then
    echo "WARNING: Some environments failed. Check /tmp/radar_install_*.log"
    echo "Re-run this script to retry failed envs (existing ones are skipped)."
    echo ""
fi

echo "============================================"
echo "  RADAR install complete (tools only)!"
echo "============================================"
echo ""
echo "  Conda environments installed:"
echo "    Base:     radar (fastp, chopper, flye, spades, polypolish, bwa,"
echo "              hmmer, blast, mlst, skani, minced, prodigal,"
echo "              sra-tools, viennarna, infernal,"
echo "              defense-finder, integron_finder, chewbbaca, resfinder,"
echo "              AMRFinderPlus, BPROM, backend requirements, nodejs)"
echo "    Separate: radar-sistr, radar-quast, radar-mobsuite,"
echo "              radar-mefinder, radar-medaka, radar-genomad, radar-busco,"
echo "              radar-plassembler, radar-ostir"
echo ""
echo "  Next step: download databases"
echo "    ./databases/download_dbs.sh"
echo ""
