#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# RADAR - Pipeline Script
# ============================================================================
# Runs the full WGS analysis pipeline on a single sample.
#
# Cases:
#   i)   Illumina only:    -1 R1.fastq.gz -2 R2.fastq.gz
#   ii)  Illumina + ONT:   -1 R1.fastq.gz -2 R2.fastq.gz -l ont.fastq.gz  (Flye -> Plassembler -> dnaapler -> Medaka -> Polypolish)
#   iii) ONT only:         -l ont.fastq.gz                     (Flye -> Plassembler -> dnaapler -> Medaka)
#   iv)  PacBio HiFi only: -l hifi.fastq.gz -p pacbio  (Flye -> Plassembler -> dnaapler; Illumina reads, if given, are ignored)
#
# Usage:
#   ./pipeline.sh -1 R1.fastq.gz -2 R2.fastq.gz -o outdir [-t threads] [-s sample_name]
#   ./pipeline.sh -1 R1.fastq.gz -2 R2.fastq.gz -l ont.fastq.gz -o outdir
#   ./pipeline.sh -l hifi.fastq.gz -p pacbio -o outdir
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_DIR="${SCRIPT_DIR}/databases"

R1="" R2="" LONG="" PLATFORM="ont" OUTDIR="" THREADS=4 SAMPLE=""

usage() {
    cat <<EOF
Usage: $0 [options]

Input (at least one required):
  -1 FILE    Illumina R1 reads (.fastq.gz)
  -2 FILE    Illumina R2 reads (.fastq.gz)
  -l FILE    Long reads - ONT or PacBio HiFi (.fastq.gz)
  -p PLAT    Long-read platform: ont (default) or pacbio

Options:
  -o DIR     Output directory (required)
  -t INT     Threads (default: 4)
  -s NAME    Sample name (default: derived from R1 or long-read filename)
  -d DIR     Database directory (default: ./databases)
  -h         Show this help

Cases:
  Illumina only:      -1 R1.fq.gz -2 R2.fq.gz -o out/
  Illumina + ONT:     -1 R1.fq.gz -2 R2.fq.gz -l ont.fq.gz -o out/
  ONT only:           -l ont.fq.gz -o out/
  PacBio HiFi only:   -l hifi.fq.gz -p pacbio -o out/
                      (Illumina reads, if also given, are ignored)
EOF
    exit 0
}

while getopts "1:2:l:p:o:t:s:d:h" opt; do
    case $opt in
        1) R1="$OPTARG" ;;
        2) R2="$OPTARG" ;;
        l) LONG="$OPTARG" ;;
        p) PLATFORM="$OPTARG" ;;
        o) OUTDIR="$OPTARG" ;;
        t) THREADS="$OPTARG" ;;
        s) SAMPLE="$OPTARG" ;;
        d) DB_DIR="$OPTARG" ;;
        h) usage ;;
        *) exit 1 ;;
    esac
done

# --------------------------------------------------------------------------
# Validate inputs
# --------------------------------------------------------------------------
if [ -z "$OUTDIR" ]; then
    echo "ERROR: Output directory required (-o)" >&2; exit 1
fi

if [ -z "$R1" ] && [ -z "$LONG" ]; then
    echo "ERROR: Provide Illumina reads (-1/-2) and/or long reads (-l)" >&2; exit 1
fi

if [ -n "$R1" ] && [ -z "$R2" ]; then
    echo "ERROR: R2 required when R1 is provided (-2)" >&2; exit 1
fi

# PacBio HiFi alone is sufficient — ignore Illumina reads if both are given
if [ -n "$LONG" ] && [ "$PLATFORM" = "pacbio" ] && [ -n "$R1" ]; then
    echo "NOTE: PacBio HiFi reads provided — Illumina reads ignored (PacBio-only assembly)" >&2
    R1="" R2=""
fi

# Determine case
if [ -n "$R1" ] && [ -n "$LONG" ]; then
    CASE="hybrid"
elif [ -n "$R1" ]; then
    CASE="illumina"
else
    CASE="longread"
fi

# Derive sample name
if [ -z "$SAMPLE" ]; then
    if [ -n "$R1" ]; then
        SAMPLE=$(basename "$R1" | sed 's/_R1.*//; s/\.fastq.*//; s/\.fq.*//')
    else
        SAMPLE=$(basename "$LONG" | sed 's/\.fastq.*//; s/\.fq.*//')
    fi
fi

# Resolve absolute paths
[ -n "$R1" ]   && R1="$(realpath "$R1")"
[ -n "$R2" ]   && R2="$(realpath "$R2")"
[ -n "$LONG" ] && LONG="$(realpath "$LONG")"
OUTDIR="$(mkdir -p "$OUTDIR" && realpath "$OUTDIR")"
DB_DIR="$(realpath "$DB_DIR")"

# Create output subdirectories
QC_DIR="${OUTDIR}/qc"
ASM_DIR="${OUTDIR}/assembly"
ANNOT_DIR="${OUTDIR}/annotation"
mkdir -p "$QC_DIR" "$ASM_DIR" "$ANNOT_DIR"

LOG="${OUTDIR}/pipeline.log"

# --------------------------------------------------------------------------
# Helper functions
# --------------------------------------------------------------------------
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }
run() { log "CMD: $*"; "$@" 2>&1 | tee -a "$LOG"; }

run_step() {
    local name=$1; shift
    log "── ${name} ──"
    if "$@" >> "$LOG" 2>&1; then
        log "  ${name} complete"
    else
        log "  ${name} FAILED (exit $?)"
        return 1
    fi
}

run_noncritical() {
    local name=$1; shift
    log "── ${name} ──"
    if "$@" >> "$LOG" 2>&1; then
        log "  ${name} complete"
    else
        log "  ${name} failed (non-critical, continuing)"
    fi
}

# Medaka polish; prints the polished FASTA path (or the draft if Medaka fails).
# --bacteria needs basecaller model info in read headers (recent Dorado output);
# older reads are rejected, so retry with automatic model selection.
run_medaka() {
    local reads=$1 draft=$2 out="${ASM_DIR}/medaka_out"
    local extra
    for extra in "--bacteria" ""; do
        rm -rf "$out"
        log "── Medaka polish ${extra} ──" >&2
        if conda run -n radar-medaka medaka_consensus \
                -i "$reads" -d "$draft" -o "$out" -t "$THREADS" $extra >> "$LOG" 2>&1 \
            && [ -s "${out}/consensus.fasta" ]; then
            log "  Medaka complete" >&2
            echo "${out}/consensus.fasta"
            return 0
        fi
    done
    log "  Medaka failed (non-critical, using unpolished draft)" >&2
    echo "$draft"
}

# Plassembler: recover small plasmids (< ~20 kb) that Flye misses. Plasmids not already in the Flye
# assembly (no Flye contig covering >=90% of them) are appended to the draft before polishing, so they
# are polished too and their short reads do not pile onto similar chromosome regions.
# Uses the raw long reads: Chopper's 1 kb minimum would drop reads from plasmids < 1 kb, and
# Plassembler applies its own read filter. Long mode for ONT/HiFi, hybrid mode with Illumina reads.
# Prints the merged FASTA path (or the draft unchanged if Plassembler fails or adds nothing).
add_plassembler_plasmids() {
    local draft=$1 out="${ASM_DIR}/plassembler_out" merged="${ASM_DIR}/flye_plus_plasmids.fasta"
    local mode=long extra=() db=(--skip_mash)
    [ -n "$R1" ] && mode=run && extra+=(-1 "$TRIMMED_R1" -2 "$TRIMMED_R2")
    [ "$PLATFORM" = "pacbio" ] && extra+=(--pacbio_model pacbio-hifi)
    compgen -G "${DB_DIR}/plassembler_db/*.msh" > /dev/null && db=(-d "${DB_DIR}/plassembler_db")
    log "── Plassembler (${mode}) ──" >&2
    if ! conda run -n radar-plassembler plassembler "$mode" -l "$LONG" "${extra[@]}" \
            --flye_directory "${ASM_DIR}/flye_out" -o "$out" -t "$THREADS" "${db[@]}" -f >> "$LOG" 2>&1; then
        log "  Plassembler failed (non-critical, using the Flye assembly)" >&2
        echo "$draft"; return 0
    fi
    local pf="${out}/plassembler_plasmids.fasta"
    if [ ! -s "$pf" ]; then
        log "  Plassembler found no plasmids" >&2
        echo "$draft"; return 0
    fi
    conda run -n radar-plassembler minimap2 -x asm5 -c "$draft" "$pf" 2>> "$LOG" \
        | awk '{c[$1]+=$4-$3; L[$1]=$2} END{for(k in c) if(c[k]>=0.9*L[k]) print k}' > "${out}/in_flye.txt"
    cp "$draft" "$merged"
    # circular contigs -> plassembler_N; linear ones (sometimes a chromosome piece Flye dropped) -> plassembler_linear_N.
    # Header descriptions are dropped (they break MOB-recon's report); copy numbers stay in plassembler_out/.
    awk 'FILENAME==ARGV[1]{s[$1]; next} /^>/{id=substr($1,2); keep=!(id in s); if(keep) print (tolower($0) ~ /circular=true/ ? ">plassembler_" : ">plassembler_linear_") id; next} keep' \
        "${out}/in_flye.txt" "$pf" >> "$merged"
    local n_new
    n_new=$(grep -c '^>plassembler_' "$merged" || true)
    log "  Plassembler: $(grep -c '^>' "$pf") contig(s), ${n_new} not in the Flye assembly added ($(grep -c '^>plassembler_linear_' "$merged" || true) linear)" >&2
    if [ "$n_new" -gt 0 ]; then echo "$merged"; else echo "$draft"; fi
}

rotate_contigs() {
    # dnaapler: start circular contigs at dnaA (chromosome), repA (plasmid) or terL (phage), so no
    # gene spans the contig end (such genes are reported as partial). Runs before polishing, so the
    # former contig ends are polished as ordinary sequence. Linear contigs are left as they are.
    local draft=$1 out="${ASM_DIR}/dnaapler_out" ign="${ASM_DIR}/dnaapler_ignore.txt"
    { awk -F'\t' '!/^#/ && $4=="N"{print $1}' "${ASM_DIR}/flye_out/assembly_info.txt" 2>/dev/null
      grep -o '^>plassembler_linear_[^ ]*' "$draft" | cut -c2-; } > "$ign"
    log "── dnaapler (rotate circular contigs) ──" >&2
    if conda run -n radar-plassembler dnaapler all -i "$draft" -o "$out" -p dnaapler -t "$THREADS" \
            --ignore "$ign" -f >> "$LOG" 2>&1 && [ -s "${out}/dnaapler_reoriented.fasta" ]; then
        echo "${out}/dnaapler_reoriented.fasta"
    else
        log "  dnaapler failed (non-critical, contigs not rotated)" >&2
        echo "$draft"
    fi
}

# --------------------------------------------------------------------------
# Print summary
# --------------------------------------------------------------------------
echo "============================================"
echo "  RADAR Pipeline"
echo "============================================"
log "Sample:   ${SAMPLE}"
log "Case:     ${CASE}"
log "Threads:  ${THREADS}"
log "Output:   ${OUTDIR}"
[ -n "$R1" ]   && log "R1:       ${R1}"
[ -n "$R2" ]   && log "R2:       ${R2}"
[ -n "$LONG" ] && log "Long:     ${LONG} (${PLATFORM})"
echo ""

# ══════════════════════════════════════════════════════════════════════════
# PHASE 1: QC & ASSEMBLY
# ══════════════════════════════════════════════════════════════════════════
log "═══ PHASE 1: QC & Assembly ═══"

TRIMMED_R1="${QC_DIR}/trimmed_R1.fastq.gz"
TRIMMED_R2="${QC_DIR}/trimmed_R2.fastq.gz"
FILTERED_LONG="${QC_DIR}/filtered_long.fastq.gz"
ASSEMBLY="${ASM_DIR}/assembly.fasta"

# --- Step 1: fastp (Illumina QC) ---
if [ -n "$R1" ]; then
    run_step "fastp (Illumina)" \
        conda run -n radar \
        fastp \
            -i "$R1" -I "$R2" \
            -o "$TRIMMED_R1" -O "$TRIMMED_R2" \
            --html "${QC_DIR}/fastp_report.html" \
            --json "${QC_DIR}/fastp_report.json" \
            --thread "$THREADS" \
            --qualified_quality_phred 20 \
            --length_required 50 \
            --detect_adapter_for_pe \
            --correction \
            --cut_front --cut_tail \
            --cut_window_size 4 \
            --cut_mean_quality 20
fi

# --- Step 1b: fastp report-only (PacBio) ---
if [ "$CASE" = "longread" ] && [ "$PLATFORM" = "pacbio" ]; then
    run_noncritical "fastp (PacBio QC report)" \
        conda run -n radar \
        fastp \
            -i "$LONG" \
            -o "${QC_DIR}/pacbio_passthrough.fastq.gz" \
            --html "${QC_DIR}/fastp_report.html" \
            --json "${QC_DIR}/fastp_report.json" \
            --disable_adapter_trimming \
            --disable_quality_filtering \
            --disable_length_filtering \
            --thread "$THREADS"
fi

# --- Step 1c: Chopper (ONT QC) ---
if [ -n "$LONG" ] && [ "$PLATFORM" = "ont" ]; then
    run_step "Chopper (ONT)" \
        bash -c "conda run -n radar chopper -q 10 --minlength 1000 --threads $THREADS -i '$LONG' | gzip > '$FILTERED_LONG'"
fi

# --- Step 2: Assembly ---
case "$CASE" in
    illumina)
        # SPAdes for short-read-only
        run_step "SPAdes assembly" \
            conda run -n radar \
            spades.py \
                --isolate \
                -1 "$TRIMMED_R1" -2 "$TRIMMED_R2" \
                -o "${ASM_DIR}/spades_out" \
                -t "$THREADS"
        # Copy best output
        if [ -f "${ASM_DIR}/spades_out/scaffolds.fasta" ]; then
            cp "${ASM_DIR}/spades_out/scaffolds.fasta" "$ASSEMBLY"
        else
            cp "${ASM_DIR}/spades_out/contigs.fasta" "$ASSEMBLY"
        fi
        ;;
    hybrid)
        # Flye -> Plassembler -> Medaka -> Polypolish
        LONG_INPUT="$FILTERED_LONG"
        [ ! -f "$LONG_INPUT" ] && LONG_INPUT="$LONG"

        # Flye
        run_step "Flye assembly" \
            conda run -n radar \
            flye \
                --nano-hq "$LONG_INPUT" \
                --out-dir "${ASM_DIR}/flye_out" \
                --threads "$THREADS"
        CURRENT_ASM="${ASM_DIR}/flye_out/assembly.fasta"

        # Plassembler: add small plasmids Flye missed (before polishing)
        CURRENT_ASM=$(add_plassembler_plasmids "$CURRENT_ASM")
        CURRENT_ASM=$(rotate_contigs "$CURRENT_ASM")

        # Medaka polish
        CURRENT_ASM=$(run_medaka "$LONG_INPUT" "$CURRENT_ASM")

        # Polypolish (short-read polishing)
        POLY_DIR="${ASM_DIR}/polypolish_out"
        mkdir -p "$POLY_DIR"

        conda run -n radar bwa index "$CURRENT_ASM" >> "$LOG" 2>&1
        conda run -n radar bwa mem -t "$THREADS" -a "$CURRENT_ASM" "$TRIMMED_R1" > "${POLY_DIR}/r1.sam" 2>> "$LOG"
        conda run -n radar bwa mem -t "$THREADS" -a "$CURRENT_ASM" "$TRIMMED_R2" > "${POLY_DIR}/r2.sam" 2>> "$LOG"

        conda run -n radar \
            polypolish filter \
                --in1 "${POLY_DIR}/r1.sam" --in2 "${POLY_DIR}/r2.sam" \
                --out1 "${POLY_DIR}/f1.sam" --out2 "${POLY_DIR}/f2.sam" >> "$LOG" 2>&1

        F1="${POLY_DIR}/f1.sam"; [ ! -f "$F1" ] && F1="${POLY_DIR}/r1.sam"
        F2="${POLY_DIR}/f2.sam"; [ ! -f "$F2" ] && F2="${POLY_DIR}/r2.sam"

        if run_noncritical "Polypolish" \
            bash -c "conda run -n radar polypolish polish '$CURRENT_ASM' '$F1' '$F2' > '${POLY_DIR}/polished.fasta'"; then
            [ -s "${POLY_DIR}/polished.fasta" ] && CURRENT_ASM="${POLY_DIR}/polished.fasta"
        fi

        cp "$CURRENT_ASM" "$ASSEMBLY"
        rm -f "${POLY_DIR}"/*.sam  # clean up large SAM files
        ;;
    longread)
        # Flye for PacBio HiFi or ONT-only
        LONG_INPUT="$LONG"
        FLYE_MODE="--nano-hq"
        if [ "$PLATFORM" = "pacbio" ]; then
            FLYE_MODE="--pacbio-hifi"
        elif [ -f "$FILTERED_LONG" ]; then
            LONG_INPUT="$FILTERED_LONG"
        fi

        run_step "Flye assembly" \
            conda run -n radar \
            flye \
                $FLYE_MODE "$LONG_INPUT" \
                --out-dir "${ASM_DIR}/flye_out" \
                --threads "$THREADS"
        CURRENT_ASM="${ASM_DIR}/flye_out/assembly.fasta"

        # Plassembler: add small plasmids Flye missed (before polishing)
        CURRENT_ASM=$(add_plassembler_plasmids "$CURRENT_ASM")
        CURRENT_ASM=$(rotate_contigs "$CURRENT_ASM")

        # ONT-only: Medaka polish (PacBio HiFi doesn't need long-read polishing)
        if [ "$PLATFORM" = "ont" ]; then
            CURRENT_ASM=$(run_medaka "$LONG_INPUT" "$CURRENT_ASM")
        fi
        cp "$CURRENT_ASM" "$ASSEMBLY"
        ;;
esac

# Normalise the assembly for the annotation tools: keep only contig names (Polypolish appends
# " polypolish" and Plassembler adds descriptions; both make MobileElementFinder fail) and order
# contigs longest first (MobileElementFinder can also fail when a small contig precedes the chromosome).
awk '/^>/{if(n!="") print n "\t" length(s) "\t" s; n=$1; s=""; next} {s=s $0} END{if(n!="") print n "\t" length(s) "\t" s}' "$ASSEMBLY" \
    | sort -t $'\t' -k2,2nr -s \
    | awk -F'\t' '{print $1; for(i=1;i<=length($3);i+=60) print substr($3,i,60)}' > "${ASSEMBLY}.tmp" \
    && mv "${ASSEMBLY}.tmp" "$ASSEMBLY"

log "Assembly: ${ASSEMBLY}"

# --- Step 2b: Assembly QC ---
run_noncritical "QUAST" \
    conda run -n radar-quast \
    quast "$ASSEMBLY" \
        -o "${ASM_DIR}/quast" \
        --min-contig 200 \
        -t "$THREADS"

run_noncritical "BUSCO" \
    conda run -n radar-busco \
    busco \
        -i "$ASSEMBLY" \
        -o busco_result \
        --out_path "${ASM_DIR}/busco" \
        -m genome \
        -l bacteria_odb10 \
        --cpu "$THREADS" \
        -f

# ══════════════════════════════════════════════════════════════════════════
# PHASE 2: ANNOTATION
# ══════════════════════════════════════════════════════════════════════════
log "═══ PHASE 2: Annotation ═══"

# --- Species ID (skani + 16S BLAST) ---
# skani needs a sketched database directory (.sketch files or sketches.db)
SKANI_DB=""
for d in "${DB_DIR}/skani" "${DB_DIR}/skani/skani-gtdb-r220-sketch" "${DB_DIR}"/skani/*/; do
    if [ -d "$d" ] && { ls "$d"/*.sketch &>/dev/null || [ -f "$d/sketches.db" ]; }; then
        SKANI_DB="$d"
        break
    fi
done
if [ -n "$SKANI_DB" ]; then
    run_noncritical "Species ID (skani)" \
        conda run -n radar \
        skani search \
            -d "$SKANI_DB" \
            -q "$ASSEMBLY" \
            -o "${ANNOT_DIR}/skani_results.tsv" \
            -t "$THREADS"
else
    log "  skani skipped (no sketch database found in ${DB_DIR}/skani)"
fi

if [ -f "${DB_DIR}/16S/16S_ribosomal_RNA.ndb" ]; then
    run_noncritical "16S BLAST" \
        conda run -n radar \
        blastn \
            -query "$ASSEMBLY" \
            -db "${DB_DIR}/16S/16S_ribosomal_RNA" \
            -out "${ANNOT_DIR}/16s_blast.tsv" \
            -outfmt "6 qseqid sseqid pident length evalue bitscore stitle" \
            -max_target_seqs 5 \
            -evalue 1e-10 \
            -num_threads "$THREADS"
fi

# --- MLST ---
run_noncritical "MLST" \
    conda run -n radar bash -c "export PERL5LIB=\$CONDA_PREFIX/lib/perl5/site_perl/5.22.0/x86_64-linux-thread-multi:\$CONDA_PREFIX/lib/perl5/site_perl/5.22.0; mlst '$ASSEMBLY' --threads '$THREADS' > '${ANNOT_DIR}/mlst.tsv'"

# --- Serotyping ---
run_noncritical "Serotyping (SISTR)" \
    conda run -n radar-sistr \
    sistr \
        -i "$ASSEMBLY" "${SAMPLE}" \
        -o "${ANNOT_DIR}/sistr_results.tsv" \
        -f tab \
        -t "$THREADS"

# --- AMRFinderPlus (critical) ---
AMRFINDER_DB_FLAG=""
if [ -d "${DB_DIR}/amrfinderplus" ]; then
    # Check if files are directly in amrfinderplus/ or in a version subdirectory
    if [ -f "${DB_DIR}/amrfinderplus/AMRProt.fa" ]; then
        AMRFINDER_DB_FLAG="-d ${DB_DIR}/amrfinderplus"
    else
        AMRFINDER_DB=$(find "${DB_DIR}/amrfinderplus" -maxdepth 1 -mindepth 1 -type d | sort -V | tail -1)
        [ -n "$AMRFINDER_DB" ] && AMRFINDER_DB_FLAG="-d ${AMRFINDER_DB}"
    fi
fi

run_step "AMRFinderPlus" \
    conda run -n radar \
    amrfinder \
        --nucleotide "$ASSEMBLY" \
        --output "${ANNOT_DIR}/amrfinder.tsv" \
        --threads "$THREADS" \
        --plus \
        $AMRFINDER_DB_FLAG

# --- Plasmid analysis (MOB-recon) ---
run_noncritical "MOB-recon" \
    conda run -n radar-mobsuite \
    mob_recon \
        -i "$ASSEMBLY" \
        -o "${ANNOT_DIR}/mob_recon" \
        --num_threads "$THREADS" \
        -f

# --- MobileElementFinder ---
mkdir -p "${ANNOT_DIR}/mefinder"
run_noncritical "MobileElementFinder" \
    conda run -n radar-mefinder \
    mefinder find \
        --contig "$ASSEMBLY" \
        --gff \
        "${ANNOT_DIR}/mefinder/mefinder_results"

# --- IntegronFinder ---
run_noncritical "IntegronFinder" \
    conda run -n radar \
    integron_finder \
        "$ASSEMBLY" \
        --outdir "${ANNOT_DIR}/integron_finder" \
        --cpu "$THREADS" \
        --local-max

# --- geNomad (prophage/plasmid) ---
if [ -d "${DB_DIR}/genomad_db" ]; then
    run_noncritical "geNomad" \
        conda run -n radar-genomad \
        genomad end-to-end \
            "$ASSEMBLY" \
            "${ANNOT_DIR}/genomad" \
            "${DB_DIR}/genomad_db" \
            --threads "$THREADS"
fi

# --- PointFinder (point mutations) ---
if [ -d "${DB_DIR}/pointfinder_db" ]; then
    # Detect species from skani results for PointFinder
    PF_SPECIES=""
    if [ -f "${ANNOT_DIR}/skani_results.tsv" ]; then
        PF_SPECIES=$(head -2 "${ANNOT_DIR}/skani_results.tsv" | tail -1 | awk -F'\t' '{print $NF}' | awk '{print tolower($1"_"$2)}' | head -1)
    fi
    if [ -n "$PF_SPECIES" ] && [ -d "${DB_DIR}/pointfinder_db/${PF_SPECIES}" ]; then
        run_noncritical "PointFinder" \
            conda run -n radar \
            python3 -m resfinder \
                -ifa "$ASSEMBLY" \
                --point \
                --db_path_point "${DB_DIR}/pointfinder_db" \
                -s "$PF_SPECIES" \
                -o "${ANNOT_DIR}/pointfinder"
    else
        log "  PointFinder skipped (species not supported or not identified)"
    fi
fi

# --- cgMLST (chewBBACA) ---
run_noncritical "cgMLST (chewBBACA)" \
    conda run -n radar \
    chewBBACA.py AlleleCall \
        -i "$ASSEMBLY" \
        -g "${DB_DIR}/cgmlst_schemas" \
        -o "${ANNOT_DIR}/cgmlst" \
        --cpu "$THREADS" \
    2>/dev/null

# --- CRISPR detection (minced) ---
run_noncritical "CRISPR (minced)" \
    bash -c "conda run -n radar minced '$ASSEMBLY' '${ANNOT_DIR}/crispr_minced.txt' '${ANNOT_DIR}/crispr_minced.gff'"

# --- DefenseFinder ---
# Prodigal first (gene prediction for DefenseFinder input)
PROTEINS="${ANNOT_DIR}/prodigal_proteins.faa"
run_noncritical "Prodigal" \
    conda run -n radar \
    prodigal \
        -i "$ASSEMBLY" \
        -a "$PROTEINS" \
        -o "${ANNOT_DIR}/prodigal_genes.gff" \
        -f gff \
        -p meta

if [ -f "$PROTEINS" ]; then
    run_noncritical "DefenseFinder" \
        conda run -n radar \
        defense-finder run \
            "$PROTEINS" \
            -o "${ANNOT_DIR}/defensefinder" \
            --workers "$THREADS"
fi

# --- ICEfinder (BLAST-based ICE detection) ---
if [ -d "${DB_DIR}/iceberg_db" ]; then
    run_noncritical "ICEfinder" \
        conda run -n radar \
        blastn \
            -query "$ASSEMBLY" \
            -db "${DB_DIR}/iceberg_db/ICEberg" \
            -out "${ANNOT_DIR}/icefinder.tsv" \
            -outfmt "6 qseqid sseqid pident length qstart qend sstart send evalue bitscore stitle" \
            -evalue 1e-10 \
            -num_threads "$THREADS"
fi

# --- Promoter analysis (BPROM) ---
if command -v bprom &>/dev/null || conda run -n radar which bprom &>/dev/null 2>&1; then
    run_noncritical "BPROM (promoter analysis)" \
        bash -c "
            # Extract upstream regions of ARGs and run BPROM
            if [ -f '${ANNOT_DIR}/amrfinder.tsv' ]; then
                mkdir -p '${ANNOT_DIR}/promoter'
                # BPROM runs on individual sequences — handled by context annotation
            fi
        "
fi

# --- RBS analysis (OSTIR) ---
# For each AMRFinderPlus hit that starts with a start codon: 51 bp upstream to 19 bp into the
# gene on its own strand (start codon at position 52), scored by OSTIR for that codon only.
# OSTIR runs in radar-ostir (ViennaRNA's py3.11 bindings conflict with mlst/perl in radar).
run_ostir_rbs() {
    local rbs="${ANNOT_DIR}/rbs"
    mkdir -p "$rbs"
    # conda run does not forward stdin, so the script goes through a file
    cat > "${rbs}/make_windows.py" <<'PYEOF'
import csv, sys
from Bio import SeqIO
from Bio.Seq import Seq
amr, asm, out = sys.argv[1:4]
contigs = {r.id: str(r.seq).upper() for r in SeqIO.parse(asm, "fasta")}
n = 0
with open(out, "w") as fh:
    for i, row in enumerate(csv.DictReader(open(amr), delimiter="\t")):
        seq = contigs.get(row["Contig id"])
        if seq is None:
            continue
        s0, e0 = int(row["Start"]) - 1, int(row["Stop"])
        if row["Strand"] == "+":
            if s0 < 51:
                continue
            w = seq[s0 - 51:s0 + 19]
        else:
            if e0 + 51 > len(seq):
                continue
            w = str(Seq(seq[e0 - 19:e0 + 51]).reverse_complement())
        if w[51:54] not in ("ATG", "GTG", "TTG"):
            continue  # partial hit or no start codon
        fh.write(f">{i}|{row['Element symbol']}|{row['Contig id']}:{row['Start']}-{row['Stop']}{row['Strand']}\n{w}\n")
        n += 1
print(f"{n} RBS windows", file=sys.stderr)
PYEOF
    conda run -n radar python "${rbs}/make_windows.py" "${ANNOT_DIR}/amrfinder.tsv" "$ASSEMBLY" \
        "${rbs}/windows.fasta" || return 1
    rm -f "${rbs}/make_windows.py"
    [ -s "${rbs}/windows.fasta" ] || return 0
    conda run -n radar-ostir ostir -i "${rbs}/windows.fasta" -t fasta -s 52 -e 52 \
        -j "$THREADS" -o "${rbs}/ostir_results.csv"
}
if [ -f "${ANNOT_DIR}/amrfinder.tsv" ]; then
    run_noncritical "OSTIR (RBS analysis)" run_ostir_rbs
fi

# --- Context annotations (sRNA via cmscan against Rfam) ---
# cmscan against full Rfam is very slow (~2h for a bacterial genome); use --rfam --cut_ga to speed up
if [ -f "${DB_DIR}/Rfam.cm" ] && [ -f "$PROTEINS" ]; then
    run_noncritical "sRNA annotation (cmscan)" \
        conda run -n radar \
        cmscan \
            --tblout "${ANNOT_DIR}/rfam_hits.tbl" \
            --noali \
            --rfam \
            --cut_ga \
            --cpu "$THREADS" \
            --fmt 2 \
            "${DB_DIR}/Rfam.cm" \
            "$ASSEMBLY"
fi

# ══════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════
log ""
log "═══ Pipeline complete ═══"
log "Sample: ${SAMPLE}"
log "Output: ${OUTDIR}"
log ""

# Print key results if available
if [ -f "${ANNOT_DIR}/amrfinder.tsv" ]; then
    ARG_COUNT=$(tail -n +2 "${ANNOT_DIR}/amrfinder.tsv" | wc -l)
    log "AMR genes found: ${ARG_COUNT}"
fi

if [ -f "${ASM_DIR}/quast/report.tsv" ]; then
    N50=$(grep "^N50" "${ASM_DIR}/quast/report.tsv" | cut -f2)
    CONTIGS=$(grep "^# contigs " "${ASM_DIR}/quast/report.tsv" | head -1 | cut -f2)
    log "Assembly: ${CONTIGS} contigs, N50=${N50}"
fi

if [ -f "${ANNOT_DIR}/mlst.tsv" ]; then
    MLST_RESULT=$(cat "${ANNOT_DIR}/mlst.tsv" | cut -f2,3)
    log "MLST: ${MLST_RESULT}"
fi

log ""
log "Full log: ${LOG}"
echo "============================================"
