# RADAR

**Resistome Analysis, Detection, Assessment & Risk**

A bioinformatics platform for whole-genome sequencing (WGS) based antimicrobial resistance analysis. RADAR takes raw Illumina, ONT, or PacBio sequencing data (or pre-assembled genomes), runs a comprehensive annotation pipeline, then uses machine learning to predict antibiotic resistance phenotypes and compute composite clinical risk scores.

---

## Features

- **24 bioinformatics tools** in isolated conda environments for reproducibility
- **Automated pipeline** with skip logic for re-runs, one-click execution, real-time progress tracking
- **ML phenotype prediction** using 107 pre-trained Random Forest models across 5 species and up to 35 antibiotics per species
- **Expression context analysis** -- goes beyond gene presence to analyze promoter strength (BPROM), ribosome binding site efficiency (OSTIR), and codon adaptation (CAI)
- **Interactive genome and plasmid maps** with ARGs, virulence factors, IS elements, prophages, and conjugation machinery
- **Biocide/metal resistance** detection via BacMet2
- **Composite risk scoring** combining ARG burden, virulence, and mobility (0-10 scale)
- **Bulk export** of all annotation results as a ZIP of TSV files

## Supported Species (ML Phenotype Prediction)

| Species | Antibiotics | Models |
|---------|------------|--------|
| *Escherichia coli* | 35 | 35 |
| *Salmonella enterica* | 20 | 20 |
| *Klebsiella pneumoniae* | 26 | 26 |
| *Staphylococcus aureus* | 13 | 13 |
| *Acinetobacter baumannii* | 13 | 13 |

Other species are fully supported for annotation; ML predictions are available for the 5 species above.

## Supported Input

| Input Type | Files | Pipeline |
|-----------|-------|----------|
| Illumina paired-end | `SAMPLE_R1.fastq.gz` + `SAMPLE_R2.fastq.gz` | fastp -> SPAdes -> annotation |
| Hybrid (Illumina + ONT) | R1 + R2 + `SAMPLE.fastq.gz` | fastp + Filtlong -> Flye -> Medaka -> Polypolish -> annotation |
| PacBio HiFi | `SAMPLE.fastq.gz` | fastp (report) -> Flye (--pacbio-hifi) -> annotation |
| ONT only | `SAMPLE.fastq.gz` | Filtlong -> Flye -> annotation |
| Pre-assembled | `SAMPLE.fasta` | annotation only (skips QC + assembly) |

Also supports: `_1`/`_2` suffix convention, SRA accession fetch, BV-BRC genome import.

## Pipeline

| Stage | Tools | Conda Env |
|-------|-------|-----------|
| QC | fastp, Filtlong | `radar-fastp`, `radar-filtlong` |
| Assembly | SPAdes, Flye, Medaka, Polypolish | `radar-spades`, `radar-flye`, `radar-medaka`, `radar-polypolish` |
| Assembly QC | QUAST, BUSCO | `radar-quast`, `radar-busco` |
| Species ID | skani (ANI vs GTDB), 16S BLAST | `radar-skani`, `radar-blast` |
| MLST | mlst | `radar-mlst` |
| AMR detection | AMRFinderPlus (v4.2.7) | `radar-amrfinder` |
| Plasmid typing | MOB-recon | `radar-mobsuite` |
| IS elements | MobileElementFinder | `radar-mefinder` |
| Integrons | IntegronFinder | `radar-integron` |
| Prophages | geNomad | `radar-genomad` |
| Point mutations | PointFinder (via ResFinder) | `radar-resfinder` |
| Serotyping | SISTR, Kleborate | `radar-serotype` |
| cgMLST | chewBBACA | `radar-cgmlst` |
| CRISPR | minced | `radar-crispr` |
| Defense systems | DefenseFinder | `radar-defense` |
| Biocide/metal | BacMet2 (blastp) | `radar-blast` |
| Gene prediction | Prodigal | `radar-prodigal` |
| Promoter | BPROM | binary |
| RBS | OSTIR | `radar-ostir` |
| sRNA | Infernal / Rfam | `radar-blast` |
| ML phenotype | scikit-learn Random Forest | `radar` (main env) |
| Risk scoring | Composite algorithm | `radar` (main env) |

## Quick Start

### Option 1: Bare-metal (recommended for bioinformatics servers)

```bash
# Clone
git clone https://github.com/tatsu1207/radar.git
cd radar

# Install all tools (24 conda environments + 8 databases)
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
docker compose up -d
```

### Access

Ports are derived from your UID for multi-user servers (see `data/ports.env`):

| Service | Default Port |
|---------|-------------|
| Frontend | `http://localhost:<PORT_FRONTEND>` |
| Backend API | `http://localhost:<PORT_BACKEND>` |
| API Docs | `http://localhost:<PORT_BACKEND>/docs` |

### First Steps

1. Open the frontend in your browser
2. Go to **Files** -- upload FASTQ/FASTA files (or fetch from SRA)
3. Click **Start** to run the pipeline (progress shown in real time)
4. Go to **Annotation** -- view results, genome maps, download reports
5. Go to **Tools > Phenotype Prediction** -- view ML-based resistance predictions

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
- **Tools**: 24 isolated conda environments (one tool per env via `install.sh`)

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

## Standalone Pipeline

For command-line usage without the web interface:

```bash
# Illumina only
./pipeline.sh -1 reads_R1.fastq.gz -2 reads_R2.fastq.gz -o results/ -t 12

# Hybrid (Illumina + ONT)
./pipeline.sh -1 reads_R1.fastq.gz -2 reads_R2.fastq.gz -l ont.fastq.gz -o results/

# PacBio HiFi only
./pipeline.sh -l hifi.fastq.gz -p pacbio -o results/
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Citation

If you use RADAR in your research, please cite:

```
RADAR: Resistome Analysis, Detection, Assessment & Risk.
[Citation details to be added upon publication.]
```
