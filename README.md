# RADAR

**Resistome Analysis, Detection, Assessment & Risk**

A bioinformatics platform for whole-genome sequencing (WGS) based antimicrobial resistance analysis. RADAR takes raw Illumina, ONT, or PacBio sequencing data (or pre-assembled genomes), runs a comprehensive annotation pipeline, then uses machine learning to predict antibiotic resistance phenotypes and compute composite clinical risk scores.

---

## Features

- **24 bioinformatics tools** in consolidated conda environments (CPU-only, no GPU required)
- **Automated pipeline** with skip logic for re-runs, one-click execution, real-time progress tracking
- **ML phenotype prediction** using 107 pre-trained Random Forest models across 5 species and up to 35 antibiotics per species
- **Expression context analysis** -- goes beyond gene presence to analyze promoter strength (BPROM), ribosome binding site efficiency (OSTIR), and codon adaptation (CAI)
- **Circular plasmid maps** grouped by cluster with ARGs, VFs, IS elements, prophages, and conjugation machinery
- **Synteny maps** showing MGE-flanked ARGs and virulence factors with adjustable flanking distance
- **Defense systems** including CRISPR-Cas, RM systems, abortive infection, ICE, and more (DefenseFinder + minced)
- **Biocide/metal resistance** detection via BacMet2
- **Composite risk scoring** combining ARG burden, virulence, and mobility (0-10 scale)
- **Per-sample TSV export** (single file with all annotations) or bulk ZIP export

## Supported Species (ML Phenotype Prediction)

| Species | Antibiotics | Models |
|---------|------------|--------|
| *Escherichia coli* | 35 | 35 |
| *Salmonella enterica* | 20 | 20 |
| *Klebsiella pneumoniae* | 26 | 26 |
| *Staphylococcus aureus* | 13 | 13 |
| *Acinetobacter baumannii* | 13 | 13 |

Other species are fully supported for annotation; ML predictions are available for the 5 species above.

### Prediction Bias Warnings

The ML models are trained on clinical/surveillance isolates from NCBI BioSample. Predictions may be unreliable in the following cases:

**Low-performance models (F1 < 0.70)** — grayed out in the UI, should not be used:

| Species | Antibiotic | F1 | Notes |
|---------|-----------|-----|-------|
| *E. coli* | nitrofurantoin | 0.07 | Too few resistant samples |
| *E. coli* | piperacillin-tazobactam | 0.47 | |
| *E. coli* | doripenem | 0.50 | Small training set |
| *E. coli* | cefepime | 0.62 | |
| *K. pneumoniae* | tigecycline | 0.48 | |
| *K. pneumoniae* | fosfomycin | 0.67 | Small training set |
| *S. aureus* | linezolid | 0.57 | |
| *S. aureus* | doxycycline | 0.62 | Small training set |

**High R-bias models (≥70% resistant in training)** — may over-predict resistance, shown with warning icon:

| Species | Antibiotic | R% in training |
|---------|-----------|----------------|
| *A. baumannii* | ceftriaxone, ciprofloxacin, ceftazidime, gentamicin, TMP-SMX, levofloxacin, tetracycline | 74–94% |
| *K. pneumoniae* | colistin, nitrofurantoin, chloramphenicol, cefotaxime, ciprofloxacin, doripenem | 71–81% |
| *E. coli* | cefazolin, trimethoprim, sulfonamides | 79–90% |
| *S. aureus* | penicillin | 90% |
| *S. enterica* | colistin | 77% |

Predictions for these antibiotics should be interpreted with caution, especially for non-clinical (environmental, commensal, or laboratory) isolates. The UI displays F1 scores, training data size, and bias warnings alongside each prediction.

## Supported Input

| Input Type | Files | Pipeline |
|-----------|-------|----------|
| Illumina paired-end | `SAMPLE_R1.fastq.gz` + `SAMPLE_R2.fastq.gz` | fastp -> SPAdes -> annotation |
| Hybrid (Illumina + ONT) | R1 + R2 + `SAMPLE_ONT.fastq.gz` | fastp + Chopper -> Flye -> Medaka -> Polypolish -> annotation |
| PacBio HiFi | `SAMPLE_PB.fastq.gz` | Flye (--pacbio-hifi) -> annotation |
| ONT only | `SAMPLE_ONT.fastq.gz` | Chopper -> Flye -> annotation |
| Pre-assembled | `SAMPLE.fasta` | annotation only (skips QC + assembly) |

### Filename Conventions

| Suffix | Platform | Example |
|--------|----------|---------|
| `_R1` or `_1` | Illumina read 1 | `SAMPLE_R1.fastq.gz` |
| `_R2` or `_2` | Illumina read 2 | `SAMPLE_R2.fastq.gz` |
| `_ONT` | ONT long read | `SAMPLE_ONT.fastq.gz` |
| `_PB` | PacBio HiFi | `SAMPLE_PB.fastq.gz` |
| *(no suffix)* | Auto-detected from FASTQ headers | `SAMPLE.fastq.gz` |

Also supports SRA accession fetch and BV-BRC genome import.

## Pipeline

| Stage | Tools | Conda Env |
|-------|-------|-----------|
| QC | fastp, Chopper | `radar` |
| Assembly | SPAdes, Flye, Polypolish | `radar` |
| Assembly (polish) | Medaka | `radar-medaka` |
| Assembly QC | QUAST, BUSCO | `radar-quast` / `radar-busco` |
| Species ID | skani (ANI vs GTDB), 16S BLAST | `radar` |
| MLST | mlst | `radar` |
| AMR detection | AMRFinderPlus (v4.2.7) | `radar` |
| Plasmid typing | MOB-recon | `radar-mobsuite` |
| IS elements | MobileElementFinder | `radar-mefinder` |
| Integrons | IntegronFinder | `radar` |
| Prophages | geNomad | `radar-genomad` |
| Point mutations | PointFinder (via ResFinder) | `radar` |
| Serotyping | SISTR, Kleborate | `radar-sistr` |
| cgMLST | chewBBACA | `radar` |
| CRISPR | minced | `radar` |
| Defense systems | DefenseFinder | `radar` |
| Biocide/metal | BacMet2 (blastp) | `radar` |
| Gene prediction | Prodigal | `radar` |
| Promoter | BPROM | binary |
| RBS | OSTIR | `radar` |
| sRNA | Infernal / Rfam | `radar` |
| ML phenotype | scikit-learn Random Forest | `radar` (main env) |
| Risk scoring | Composite algorithm | `radar` (main env) |

> **Note:** RADAR runs entirely on CPU. No GPU is required. Tools like Medaka and geNomad use CPU-only builds of PyTorch and TensorFlow respectively.

## Quick Start

### Option 1: Bare-metal (recommended for bioinformatics servers)

```bash
# Clone
git clone https://github.com/tatsu1207/radar.git
cd radar

# Install all tools (6 conda environments + 8 databases, CPU-only)
./install.sh

# Start all services
./start_dev.sh

# Stop
./stop_dev.sh
```

### Option 2: Docker

```bash
git clone https://github.com/tatsu1207/radar.git
cd radar
./docker-start.sh    # start (UID-based ports, multi-user safe)
./docker-stop.sh     # stop
```

The first run pulls ~13 GB of images (the worker image contains all bioinformatics tools). Subsequent starts are instant. Reference databases (~10 GB) are stored in a Docker volume and downloaded on first pipeline run.

**Optional: skani GTDB database** — For more accurate species identification via ANI (instead of 16S BLAST fallback), install the skani GTDB sketch database (~30 GB compressed, ~50 GB uncompressed):

```bash
docker compose exec worker bash -c "
  mkdir -p /databases/skani &&
  curl -L -o /databases/skani/skani_gtdb_r226-v0.3.tar.gz \
    http://faust.compbio.cs.cmu.edu/skani-files/skani_gtdb_r226-v0.3.tar.gz &&
  tar xzf /databases/skani/skani_gtdb_r226-v0.3.tar.gz -C /databases/skani &&
  rm /databases/skani/skani_gtdb_r226-v0.3.tar.gz
"
```

**Multi-user isolation:** `docker-start.sh` assigns unique ports, container names, and volumes per user (based on UID), so multiple users on the same machine can run RADAR simultaneously without conflicts.

### Access

Ports are derived from your UID for multi-user servers:

| Service | Port | Example (UID=1002) |
|---------|------|--------------------|
| Frontend | 7200 + UID | `http://localhost:8202` |
| Backend API | 7210 + UID | `http://localhost:8212` |
| API Docs | 7210 + UID | `http://localhost:8212/docs` |

### First Steps

1. Open the frontend in your browser
2. Go to **Files** -- upload FASTQ/FASTA files (or fetch from SRA)
3. Click **Start** to run the pipeline (progress shown in real time)
4. Go to **Annotation** -- click a sample to view per-sample results (Summary, Resistance Genes, Plasmids, Mobile Elements, Defense Systems, Virulence), download per-sample TSV
5. Go to **Tools > Phenotype Prediction** -- view ML-based resistance predictions with multi-select filters

## Architecture

```
Frontend (Next.js 14)
    |
    v
Backend API (FastAPI)
    |         |
    v         v
PostgreSQL   Redis
             |
     +-------+-------+
     |               |
Pipeline Worker   Default Worker
(concurrency=1)   (concurrency=4)
 - QC & Assembly   - SRA downloads
 - Annotation      - BV-BRC fetches
 - ML prediction
```

- **Frontend**: Next.js 14, React 18, TypeScript, Tailwind CSS, Recharts, CGView
- **Backend**: Python 3.11, FastAPI, SQLAlchemy, Pydantic
- **Workers**: Celery with Redis broker; pipeline queue (1 at a time) + default queue (parallel)
- **Database**: PostgreSQL 16
- **Tools**: 9 conda environments (1 base + 8 separate for dependency conflicts, CPU-only, via `install.sh`)

## Project Structure

```
radar/
  backend/
    app/
      api/           # REST endpoints (analysis, file_manager, results, metadata)
      core/          # Pipeline modules (qc, assembly, arg_detect, plasmid, ml_phenotype, bacmet, ...)
      models/        # SQLAlchemy ORM models
      schemas/       # Pydantic request/response schemas
  frontend/
    src/
      app/           # Next.js pages (files, results, metadata, tools, samples)
      components/    # React components (PlasmidMap, LinearGenomeMap, ARGTable, ...)
      lib/api.ts     # Backend API client
  install.sh         # Install all conda envs + databases
  pipeline.sh        # Standalone CLI pipeline (no web UI)
  start_dev.sh       # Start all services
  stop_dev.sh        # Stop all services
  databases/         # Reference databases (auto-downloaded by install.sh)
```

## Command-Line Tools

RADAR also provides standalone scripts for installation and analysis without the web interface.

### install.sh — Environment & Database Setup

Installs 9 conda environments and downloads 8 reference databases. All tools are CPU-only (no GPU required). Safe to re-run: existing environments are skipped automatically.

```bash
# Default: install everything in ./databases
./install.sh

# Custom database directory and thread count
./install.sh -d /path/to/databases -t 8
```

**What it installs:**
- **Base env (`radar`)**: fastp, Chopper, SPAdes, Flye, Polypolish, AMRFinderPlus (v4.2.7 binary), mlst, skani, IntegronFinder, chewBBACA, minced, DefenseFinder, BLAST, Prodigal, OSTIR, ResFinder, sra-tools, Infernal
- **Separate envs**: `radar-sistr` (SISTR/Kleborate), `radar-quast` (QUAST), `radar-mobsuite` (MOB-suite), `radar-mefinder` (MobileElementFinder), `radar-medaka` (Medaka, CPU-only PyTorch), `radar-genomad` (geNomad, CPU-only TensorFlow), `radar-busco` (BUSCO)
- **8 databases**: AMRFinderPlus DB, geNomad DB (~3.5 GB), skani GTDB sketch (~1.5 GB), NCBI 16S rRNA, MOB-suite DB, PointFinder DB, ResFinder DB, Rfam CM, DefenseFinder models
- **Optional**: BPROM binary (if found at `/tmp/bprom`)

**Requirements**: mamba (Miniforge), ~10 GB disk for databases, ~8 GB for conda envs. No GPU needed.

### pipeline.sh — Standalone Analysis Pipeline

Runs the full annotation pipeline from the command line. Supports Illumina, hybrid (Illumina + ONT), and PacBio HiFi input.

```bash
# Illumina paired-end
./pipeline.sh -1 reads_R1.fastq.gz -2 reads_R2.fastq.gz -o results/ -t 12

# Hybrid assembly (Illumina + ONT)
./pipeline.sh -1 reads_R1.fastq.gz -2 reads_R2.fastq.gz -l ont.fastq.gz -o results/

# PacBio HiFi only
./pipeline.sh -l hifi.fastq.gz -p pacbio -o results/
```

**Options:**
| Flag | Description |
|------|-------------|
| `-1` | Illumina R1 reads (FASTQ or FASTQ.GZ) |
| `-2` | Illumina R2 reads (FASTQ or FASTQ.GZ) |
| `-l` | Long reads: ONT or PacBio (FASTQ or FASTQ.GZ) |
| `-p` | Long-read platform: `ont` (default) or `pacbio` |
| `-o` | Output directory (default: `./results`) |
| `-t` | Threads (default: 4) |
| `-d` | Database directory (default: `./databases`) |

**Pipeline flow:**
1. **QC**: fastp (Illumina) / Chopper (ONT)
2. **Assembly**: SPAdes (Illumina) / Flye + Medaka + Polypolish (hybrid) / Flye (long-read)
3. **Assembly QC**: QUAST + BUSCO
4. **Annotation**: AMRFinderPlus, MOB-recon, MobileElementFinder, IntegronFinder, geNomad, species ID, MLST, serotyping, CRISPR, DefenseFinder, BacMet2, promoter/RBS analysis

Output is written to the specified directory with subdirectories per analysis step.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Citation

If you use RADAR in your research, please cite:

```
RADAR: Resistome Analysis, Detection, Assessment & Risk.
[Citation details to be added upon publication.]
```
