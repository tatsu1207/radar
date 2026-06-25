#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# RADAR - Reference Database Download Script
# ============================================================================
# Downloads all reference databases required by RADAR.
# Run this AFTER install.sh has created the conda environments.
#
# Usage: ./databases/download_dbs.sh [-d /path/to/databases] [-t threads]
#
# Databases downloaded:
#   1. AMRFinderPlus       (~1 GB)   - ARG/virulence detection
#   2. geNomad             (~3.5 GB) - Prophage/plasmid detection
#   3. 16S rRNA BLAST      (~50 MB)  - Species ID fallback
#   4. MOB-suite           (~1 GB)   - Plasmid typing
#   5. PointFinder         (~10 MB)  - Point mutation detection
#   6. ResFinder           (~10 MB)  - Resistance gene detection
#   7. Rfam                (~500 MB) - sRNA annotation (cmscan)
#   8. DefenseFinder       (~100 MB) - Defense system models
#   9. cgMLST schemas      (~1-5 GB) - Core-genome MLST (chewBBACA via Chewie-NS)
#  10. skani GTDB          (~30 GB)  - Species ID via ANI (OPTIONAL, skipped by default)
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_DIR="${SCRIPT_DIR}"
THREADS=4

while getopts "d:t:h" opt; do
    case $opt in
        d) DB_DIR="$OPTARG" ;;
        t) THREADS="$OPTARG" ;;
        h)
            echo "Usage: $0 [-d database_dir] [-t threads]"
            echo "  -d  Database directory (default: ./databases)"
            echo "  -t  Threads for database indexing (default: 4)"
            exit 0
            ;;
        *) exit 1 ;;
    esac
done

echo "============================================"
echo "  RADAR - Reference Database Download"
echo "============================================"
echo "  Database dir: ${DB_DIR}"
echo ""

mkdir -p "${DB_DIR}"
FAIL=0

# -------------------------------------------------------------------
# 1. AMRFinderPlus database
# -------------------------------------------------------------------
echo -n "  [1/10] AMRFinderPlus database..."
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
            echo "    FAILED (see /tmp/radar_db_amrfinder.log)"
            FAIL=1
        fi
    fi
fi

# -------------------------------------------------------------------
# 2. geNomad database (~3.5 GB)
# -------------------------------------------------------------------
echo -n "  [2/10] geNomad database..."
if [ -d "${DB_DIR}/genomad_db" ]; then
    echo " exists"
else
    if conda run -n radar-genomad genomad download-database "${DB_DIR}" > /tmp/radar_db_genomad.log 2>&1; then
        echo " done"
    else
        echo " FAILED (see /tmp/radar_db_genomad.log)"
        FAIL=1
    fi
fi

# -------------------------------------------------------------------
# 3. NCBI 16S rRNA BLAST database
# -------------------------------------------------------------------
echo -n "  [3/10] 16S rRNA BLAST database..."
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
        FAIL=1
    fi
fi

# -------------------------------------------------------------------
# 4. MOB-suite database
# -------------------------------------------------------------------
echo -n "  [4/10] MOB-suite database..."
if conda run -n radar-mobsuite mob_init > /tmp/radar_db_mobsuite.log 2>&1; then
    echo " done"
else
    echo " FAILED (will auto-download on first run)"
fi

# -------------------------------------------------------------------
# 5. PointFinder database
# -------------------------------------------------------------------
echo -n "  [5/10] PointFinder database..."
if [ -d "${DB_DIR}/pointfinder_db" ]; then
    echo " exists"
else
    if git clone --quiet https://bitbucket.org/genomicepidemiology/pointfinder_db.git "${DB_DIR}/pointfinder_db" 2>/dev/null; then
        echo " done"
    else
        echo " FAILED"
        FAIL=1
    fi
fi

# -------------------------------------------------------------------
# 6. ResFinder database
# -------------------------------------------------------------------
echo -n "  [6/10] ResFinder database..."
if [ -d "${DB_DIR}/resfinder_db" ]; then
    echo " exists"
else
    if git clone --quiet https://bitbucket.org/genomicepidemiology/resfinder_db.git "${DB_DIR}/resfinder_db" 2>/dev/null; then
        echo " done"
    else
        echo " FAILED"
        FAIL=1
    fi
fi

# -------------------------------------------------------------------
# 7. Rfam CM database (for sRNA annotation via cmscan)
# -------------------------------------------------------------------
echo -n "  [7/10] Rfam database..."
if [ -f "${DB_DIR}/Rfam.cm" ]; then
    echo " exists"
else
    if curl -sL -o "${DB_DIR}/Rfam.cm.gz" "https://ftp.ebi.ac.uk/pub/databases/Rfam/CURRENT/Rfam.cm.gz" \
        && gunzip "${DB_DIR}/Rfam.cm.gz" \
        && conda run -n radar cmpress "${DB_DIR}/Rfam.cm" > /dev/null 2>&1; then
        echo " done"
    else
        echo " FAILED"
        FAIL=1
    fi
fi

# -------------------------------------------------------------------
# 8. DefenseFinder models
# -------------------------------------------------------------------
echo -n "  [8/10] DefenseFinder models..."
if conda run -n radar defense-finder update > /tmp/radar_db_defense.log 2>&1; then
    echo " done"
else
    echo " FAILED (see /tmp/radar_db_defense.log)"
    FAIL=1
fi

# -------------------------------------------------------------------
# 9. cgMLST schemas (chewBBACA via Chewie-NS)
# -------------------------------------------------------------------
echo "  [9/10] cgMLST schemas (chewBBACA)..."
CGMLST_DIR="${DB_DIR}/cgmlst_schemas"
mkdir -p "${CGMLST_DIR}"

# Species available on Chewie-NS: species_id schema_id local_dir_name
CGMLST_SPECIES=(
    "10:1:ecoli:Escherichia coli"
    "14:1:salmonella:Salmonella enterica"
    "6:1:campylobacter:Campylobacter jejuni"
    "18:1:listeria:Listeria monocytogenes"
)

for entry in "${CGMLST_SPECIES[@]}"; do
    IFS=':' read -r sp_id sc_id dir_name sp_label <<< "$entry"
    if [ -d "${CGMLST_DIR}/${dir_name}" ]; then
        echo "    SKIP  ${sp_label} (already exists)"
    else
        echo -n "    ...   ${sp_label}"
        if conda run -n radar chewBBACA.py DownloadSchema \
            --species-id "$sp_id" --schema-id "$sc_id" \
            --download-folder "${CGMLST_DIR}/${dir_name}" \
            --cpu "${THREADS}" \
            > /tmp/radar_db_cgmlst_${dir_name}.log 2>&1; then
            echo -e "\r    OK    ${sp_label}"
        else
            echo -e "\r    FAIL  ${sp_label} (see /tmp/radar_db_cgmlst_${dir_name}.log)"
            FAIL=1
        fi
    fi
done

# S. aureus cgMLST from pubMLST (1716 loci, scheme 20)
if [ -d "${CGMLST_DIR}/saureus" ]; then
    echo "    SKIP  Staphylococcus aureus (already exists)"
else
    echo -n "    ...   Staphylococcus aureus (pubMLST)"
    SAUREUS_TMP="${CGMLST_DIR}/saureus_tmp"
    mkdir -p "${SAUREUS_TMP}"
    if conda run -n radar python -c "
import requests, sys, os
base = 'https://rest.pubmlst.org/db/pubmlst_saureus_seqdef'
r = requests.get(f'{base}/schemes/20', timeout=30)
if not r.ok:
    sys.exit(1)
loci = r.json().get('loci', [])
out_dir = '${SAUREUS_TMP}'
ok = 0
for url in loci:
    locus_id = url.split('/')[-1]
    r2 = requests.get(f'{url}/alleles_fasta', timeout=30)
    if r2.ok and r2.text.startswith('>'):
        with open(os.path.join(out_dir, f'{locus_id}.fasta'), 'w') as f:
            f.write(r2.text)
        ok += 1
print(f'Downloaded {ok}/{len(loci)} loci', file=sys.stderr)
if ok < len(loci) * 0.9:
    sys.exit(1)
" > /tmp/radar_db_cgmlst_saureus.log 2>&1 \
    && conda run -n radar chewBBACA.py PrepExternalSchema \
        -g "${SAUREUS_TMP}" \
        -o "${CGMLST_DIR}/saureus" \
        --cpu "${THREADS}" \
        >> /tmp/radar_db_cgmlst_saureus.log 2>&1; then
        rm -rf "${SAUREUS_TMP}"
        echo -e "\r    OK    Staphylococcus aureus (pubMLST)"
    else
        rm -rf "${SAUREUS_TMP}"
        echo -e "\r    FAIL  Staphylococcus aureus (see /tmp/radar_db_cgmlst_saureus.log)"
        FAIL=1
    fi
fi

# K. pneumoniae cgMLST from BIGSdb Pasteur (2752 loci, scheme 19)
if [ -d "${CGMLST_DIR}/klebsiella" ]; then
    echo "    SKIP  Klebsiella pneumoniae (already exists)"
else
    echo -n "    ...   Klebsiella pneumoniae (BIGSdb Pasteur)"
    KLEB_TMP="${CGMLST_DIR}/klebsiella_tmp"
    mkdir -p "${KLEB_TMP}"
    if conda run -n radar python -c "
import requests, sys, os
base = 'https://bigsdb.pasteur.fr/api/db/pubmlst_klebsiella_seqdef'
r = requests.get(f'{base}/schemes/19', timeout=30)
if not r.ok:
    sys.exit(1)
loci = r.json().get('loci', [])
out_dir = '${KLEB_TMP}'
ok = 0
for url in loci:
    locus_id = url.split('/')[-1]
    r2 = requests.get(f'{url}/alleles_fasta', timeout=30)
    if r2.ok and r2.text.startswith('>'):
        with open(os.path.join(out_dir, f'{locus_id}.fasta'), 'w') as f:
            f.write(r2.text)
        ok += 1
print(f'Downloaded {ok}/{len(loci)} loci', file=sys.stderr)
if ok == 0:
    print('BIGSdb Pasteur requires authentication for allele data', file=sys.stderr)
    sys.exit(1)
" > /tmp/radar_db_cgmlst_klebsiella.log 2>&1 \
    && conda run -n radar chewBBACA.py PrepExternalSchema \
        -g "${KLEB_TMP}" \
        -o "${CGMLST_DIR}/klebsiella" \
        --cpu "${THREADS}" \
        >> /tmp/radar_db_cgmlst_klebsiella.log 2>&1; then
        rm -rf "${KLEB_TMP}"
        echo -e "\r    OK    Klebsiella pneumoniae (BIGSdb Pasteur)"
    else
        rm -rf "${KLEB_TMP}"
        echo -e "\r    FAIL  Klebsiella pneumoniae (may require BIGSdb authentication)"
    fi
fi

# -------------------------------------------------------------------
# 10. skani GTDB sketch database (OPTIONAL — ~30 GB)
# -------------------------------------------------------------------
echo "  [10/10] skani GTDB database... skipped (30 GB, optional)"
echo "         To install manually:"
echo "           mkdir -p ${DB_DIR}/skani"
echo "           curl -L -o ${DB_DIR}/skani/skani_gtdb_r226-v0.3.tar.gz \\"
echo "             http://faust.compbio.cs.cmu.edu/skani-files/skani_gtdb_r226-v0.3.tar.gz"
echo "           tar xzf ${DB_DIR}/skani/skani_gtdb_r226-v0.3.tar.gz -C ${DB_DIR}/skani"
echo "           rm ${DB_DIR}/skani/skani_gtdb_r226-v0.3.tar.gz"

# -------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------
echo ""
if [ "${FAIL}" -eq 1 ]; then
    echo "WARNING: Some databases failed to download."
    echo "Re-run this script to retry (existing databases are skipped)."
    echo ""
fi

echo "============================================"
echo "  Database download complete!"
echo "============================================"
echo ""
echo "  Location: ${DB_DIR}"
echo ""
echo "  Databases:"
echo "    AMRFinderPlus  : ${DB_DIR}/amrfinderplus"
echo "    geNomad        : ${DB_DIR}/genomad_db"
echo "    16S rRNA       : ${DB_DIR}/16S"
echo "    MOB-suite      : (managed by mob_suite)"
echo "    PointFinder    : ${DB_DIR}/pointfinder_db"
echo "    ResFinder      : ${DB_DIR}/resfinder_db"
echo "    Rfam           : ${DB_DIR}/Rfam.cm"
echo "    DefenseFinder  : (managed by defense-finder)"
echo "    cgMLST schemas : ${DB_DIR}/cgmlst_schemas"
echo "    skani GTDB     : (optional, see above)"
echo ""
