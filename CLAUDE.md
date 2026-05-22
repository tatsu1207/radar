# RADAR - Claude Reference

## What is RADAR?

**RADAR (Resistome Analysis, Detection, Assessment, and Risk)** is a web platform for bacterial whole-genome sequencing (WGS) antibiotic resistance analysis. It takes raw Illumina or long-read (ONT/PacBio) sequencing reads, or pre-assembled genomes, and runs them through a multi-step bioinformatics pipeline to detect resistance genes, characterize their regulatory context (promoters, RBS), identify mobile genetic elements, virulence factors, and plasmids, then produces a composite clinical risk score.

## Tech Stack

- **Backend**: Python 3.11, FastAPI, Celery, SQLAlchemy, PostgreSQL 16, Redis
- **Frontend**: Next.js 14, React 18, TypeScript, Tailwind CSS, Recharts
- **Package manager**: mamba (Miniforge)
- **Deployment**: Docker Compose or bare-metal via conda environment

## Project Structure

```
radar/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI entry point
│   │   ├── celery_app.py      # Celery task queue config
│   │   ├── config.py          # Settings (DB, Redis, paths)
│   │   ├── db.py              # Database connection
│   │   ├── api/               # REST API routes
│   │   │   ├── projects.py    # Project CRUD
│   │   │   ├── samples.py     # Sample CRUD
│   │   │   ├── upload.py      # FASTQ/FASTA file upload
│   │   │   ├── file_manager.py # File Manager (upload, SRA, BV-BRC, metadata TSV)
│   │   │   ├── analysis.py    # Pipeline trigger & job tracking
│   │   │   ├── results.py     # ARG/plasmid/mobility/risk results
│   │   │   └── metadata.py    # Sample metadata & AST data
│   │   ├── core/              # Bioinformatics pipeline modules
│   │   │   ├── pipeline.py    # Main orchestrator
│   │   │   ├── qc.py          # Read QC (fastp)
│   │   │   ├── assembly.py    # Genome assembly (SPAdes/Flye/Medaka/Polypolish)
│   │   │   ├── arg_detect.py  # ARG detection (AMRFinderPlus only)
│   │   │   ├── promoter.py    # Promoter analysis (BPROM, UP element)
│   │   │   ├── rbs.py         # Ribosome binding site analysis (OSTIR)
│   │   │   ├── plasmid.py     # Plasmid analysis (MOB-recon)
│   │   │   ├── mobility.py    # IS detection (MobileElementFinder)
│   │   │   ├── virulence.py   # Virulence factor detection (AMRFinderPlus --organism)
│   │   │   ├── phenotype.py   # Resistance phenotype prediction
│   │   │   ├── risk.py        # Composite risk scoring
│   │   │   ├── sra.py         # SRA download (prefetch + fasterq-dump)
│   │   │   ├── bvbrc.py       # BV-BRC genome fetch
│   │   │   └── tracking.py    # Resistome matrix & clustering
│   │   ├── models/models.py   # SQLAlchemy ORM models
│   │   └── schemas/           # Pydantic request/response schemas
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx                        # Dashboard
│   │   │   ├── projects/[id]/files/page.tsx    # File Manager page
│   │   │   ├── projects/[id]/page.tsx          # Project detail
│   │   │   └── samples/[id]/page.tsx           # Sample detail (tabbed results)
│   │   ├── components/
│   │   │   ├── FileManagerTable.tsx     # Main file manager table
│   │   │   ├── SRAFetchDialog.tsx       # SRR accession input dialog
│   │   │   ├── BVBRCFetchDialog.tsx     # BV-BRC genome ID fetch dialog
│   │   │   ├── MetadataTSVUpload.tsx    # TSV upload + preview
│   │   │   └── ...                      # Other components
│   │   └── lib/api.ts         # Backend API client
│   └── package.json
├── databases/
│   └── download_dbs.sh        # Reference database download script
├── docker-compose.yml
├── setup_ubuntu.sh            # Bare-metal setup (mamba, no sudo)
├── start_dev.sh               # Start all services locally
├── stop_dev.sh                # Stop all services
└── tests/
```

## Pipeline Workflow

Based on the research methodology. For FASTQ input all steps run. For FASTA input (including BV-BRC pre-assembled), steps 1-3 are skipped.

1. **QC** - fastp: adapter trimming, quality filtering (Illumina); Filtlong: ONT long-read filtering
2. **Assembly** - SPAdes (Illumina-only), Flye + Medaka + Polypolish (hybrid), Flye (long-read-only; --nano-hq for ONT, --pacbio-hifi for PacBio)
3. **Assembly QC** - QUAST + BUSCO: assembly quality metrics and genome completeness
4. **ARG detection** - AMRFinderPlus: resistance gene identification
5. **Promoter analysis** - extract 500bp upstream of each ARG, run BPROM for LDF scores, TF binding site count, promoter-to-ARG distance, UP element AT-rich ratio (20bp upstream of predicted promoter)
6. **RBS analysis** - extract -51bp to +19bp relative to each ARG start codon, run OSTIR for expression level, dG_total, dG_mRNA
7. **MGE detection** - MobileElementFinder (`mefinder`): IS elements within 5kbp of each ARG, recording IS count, nearest IS distance, strand orientation consistency
8. **Plasmid analysis** - MOB-recon: plasmid identification, replicon typing, mobility classification; cross-references ARGs as plasmid-borne
9. **Virulence** - virulence factor detection
10. **Phenotype prediction** - rule-based SIR prediction from detected ARGs
11. **Risk scoring** - composite score (0-10) from ARG burden, virulence, and mobility; categories: low/medium/high/critical

## Bioinformatics Tools

**One tool per conda environment (installed via `install.sh`):**

| Conda Env | Tool | Purpose |
|-----------|------|---------|
| radar-fastp | fastp | Adapter trimming and quality filtering (Illumina) |
| radar-filtlong | Filtlong | ONT long-read quality filtering |
| radar-spades | SPAdes | Short-read genome assembly |
| radar-flye | Flye | Long-read genome assembly (ONT/PacBio) |
| radar-medaka | Medaka | Long-read polishing (pip) |
| radar-polypolish | Polypolish + BWA | Short-read polishing for hybrid assembly |
| radar-quast | QUAST | Assembly quality assessment |
| radar-busco | BUSCO | Genome completeness assessment (pip from gitlab) |
| radar-amrfinder | AMRFinderPlus | ARG detection (GitHub binary v4.2.7 + HMMER/BLAST) |
| radar-mobsuite | MOB-suite | Plasmid reconstruction and typing (pip) |
| radar-mefinder | MobileElementFinder | Insertion sequence detection (pip, CLI: `mefinder find`) |
| radar-mlst | mlst | Multi-locus sequence typing |
| radar-skani | skani | Species ID via ANI against GTDB |
| radar-integron | IntegronFinder | Integron detection (pip) |
| radar-genomad | geNomad | Prophage/plasmid detection (pip) |
| radar-serotype | SISTR + Kleborate | In silico serotyping |
| radar-cgmlst | chewBBACA | Core-genome MLST (pip) |
| radar-crispr | minced | CRISPR array detection |
| radar-defense | DefenseFinder | Bacterial defense system detection (pip) |
| radar-blast | BLAST + Infernal | Nucleotide searches (16S, ICEberg, sRNA/Rfam) |
| radar-prodigal | Prodigal | Gene prediction (used by DefenseFinder, context annotations) |
| radar-ostir | OSTIR + ViennaRNA | RBS translation initiation rate prediction (pip) |
| radar-resfinder | ResFinder | PointFinder point mutations (pip) |
| radar-sra | sra-tools | Download FASTQ from SRA (prefetch + fasterq-dump) |

**Installed from binary (optional):**

| Tool | Purpose |
|------|---------|
| BPROM | Bacterial promoter prediction (LDF scores, TF binding sites). Linux binary at `/tmp/bprom`, copied to conda bin during setup |

## File Manager

The File Manager is the primary data ingestion interface, accessed at `/projects/{id}/files`.

### Data Sources

1. **Direct upload** - drag-drop or browse `.fastq.gz` files; filenames auto-parsed into sample IDs
2. **SRA fetch** - enter SRR accession(s); uses `prefetch` + `fasterq-dump` via Celery task; auto-detects paired vs single-end
3. **BV-BRC fetch** - enter BV-BRC genome ID(s); fetches pre-assembled FASTA via BV-BRC REST API (`application/dna+fasta`); skips QC/assembly in pipeline
4. **Metadata TSV upload** - tab-separated file mapping sample_id to metadata fields

### Table Layout

Each row = one sample. Columns: Sample ID, Illumina R1, Illumina R2, Long Read (ONT/PacBio), Source, Metadata status, Actions.

### Filename Parsing Convention

```
{sample_id}_R1.fastq.gz   → pair=R1, platform=illumina
{sample_id}_R2.fastq.gz   → pair=R2, platform=illumina
{sample_id}_ONT.fastq.gz  → pair=long_read, platform=ont
{sample_id}_PB.fastq.gz   → pair=long_read, platform=pacbio
```

### Metadata TSV Format

```
sample_id    species          source    collection_date    location
SAMPLE001    E. coli          blood     2026-01-15         Ward A
SAMPLE002    K. pneumoniae    urine     2026-01-16         ICU
```

Known columns map to Metadata model fields; extra columns go into `custom_json`.

### File Manager API

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/projects/{id}/file-manager` | GET | All samples with file slot status |
| `/api/projects/{id}/file-manager/upload` | POST | Bulk upload files, auto-create samples |
| `/api/projects/{id}/file-manager/metadata` | POST | Upload metadata TSV |
| `/api/projects/{id}/file-manager/sra` | POST | Submit SRR accession(s) for download |
| `/api/projects/{id}/file-manager/sra` | GET | List SRA download jobs + progress |
| `/api/projects/{id}/file-manager/bvbrc` | POST | Fetch genome(s) by BV-BRC genome ID |
| `/api/projects/{id}/file-manager/bvbrc` | GET | List BV-BRC fetch jobs + status |
| `/api/projects/{id}/file-manager/files/{file_id}` | DELETE | Remove a single file |
| `/api/projects/{id}/file-manager/samples/{sample_id}` | DELETE | Remove sample + all files |

## Database Models

### Existing (updated)

- **Project** - container for related samples
- **Sample** - individual sequencing sample; status: pending → qc → assembling → annotating → complete/failed
- **SampleFile** - files with pair info (R1/R2/single/long_read/assembly), platform (illumina/ont/pacbio), source (upload/sra/bvbrc), original_filename
- **Metadata** - sample metadata (source, date, location, species, custom_json)
- **AnalysisJob** - pipeline execution tracking
- **ARGResult** - detected resistance genes (gene, drug class, mechanism, identity%, coverage%, contig, database source, plasmid flag)
- **VirulenceResult** - virulence factors
- **PlasmidResult** - plasmids (replicon type, mobility, transferability)
- **RiskScore** - ARG/VF/mobility sub-scores and composite score with risk category
- **ASTResult** - phenotypic antibiotic susceptibility test results (SIR)

### New models

- **PromoterResult** - linked to ARGResult; LDF score, TF binding site count, promoter-to-ARG distance (bp), UP element AT-rich ratio
- **RBSResult** - linked to ARGResult; OSTIR expression level, dG_total, dG_mRNA
- **MobilityResult** (updated) - linked to ARGResult; IS elements from MobileElementFinder, IS count within 5kbp, nearest IS distance, orientation consistency (boolean)
- **SRADownload** - tracks SRA download jobs; srr_accession, status (queued/downloading/complete/failed), progress (0-100%), linked to project and sample
- **BVBRCFetch** - tracks BV-BRC fetch jobs; genome_id, status, linked to project and sample

### Enums

- **PairType**: R1, R2, single, assembly, long_read
- **SequencingPlatform**: illumina, ont, pacbio
- **FileSource**: upload, sra, bvbrc
- **SRADownloadStatus**: queued, downloading, complete, failed

## Risk Scoring Algorithm

- **ARG score (0-10)**: gene count (0-4pts) + drug class diversity (0-3pts) + WHO critically important antimicrobial genes (0-3pts)
- **VF score (0-10)**: VF count (0-5pts) + high-concern categories (0-5pts)
- **Mobility score (0-10)**: transferable plasmids (0-3pts) + IS/integrons (0-3pts) + mobile ARGs (0-4pts)
- **Composite**: weighted average → low (<2.5), medium (2.5-5.0), high (5.0-7.5), critical (>=7.5)

## Running the Platform

**With Docker:**
```bash
docker compose up
```

**Without Docker (bare-metal):**
```bash
./setup_ubuntu.sh    # one-time setup
./start_dev.sh       # start all services
./stop_dev.sh        # stop all services
```

Ports are derived from UID for multi-user machines (defined in `data/ports.env`): frontend=7200+UID, backend=7210+UID, PostgreSQL=7220+UID, Redis=7230+UID.
