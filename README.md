# RADAR

**Resistome Analysis, Detection, and Assessment Resource**

A unified web platform for bacterial whole-genome sequencing (WGS) antibiotic resistance analysis. RADAR integrates multiple bioinformatics tools into a single, streamlined workflow that takes raw sequencing reads through to comprehensive resistance profiling and clinical risk assessment.

---

## Features

- **Antibiotic Resistance Gene (ARG) Detection** -- Identify resistance genes using AMRFinderPlus, ABRicate (CARD, ResFinder, MEGARes), and consensus calling across databases.
- **Plasmid Analysis** -- Detect and reconstruct plasmid sequences, classify replicon types, and assess plasmid-mediated resistance using MOB-suite and PlasmidFinder.
- **Mobility Assessment** -- Evaluate the horizontal gene transfer potential of detected ARGs by analyzing their genomic context (integrons, transposons, insertion sequences, conjugative elements).
- **Risk Scoring** -- Composite risk assessment that weighs resistance gene identity, mobility potential, host range, clinical relevance, and co-resistance patterns.
- **Interactive Dashboards** -- Visualize resistance profiles, gene maps, phylogenetic context, and epidemiological trends through an intuitive web interface.
- **Project Management** -- Organize samples into projects, attach metadata, track analysis progress, and export publication-ready reports.
- **Batch Processing** -- Upload and analyze hundreds of samples in parallel with Celery-based task queuing.
- **REST API** -- Fully documented API for programmatic access and integration with existing LIMS/EHR systems.

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (v20.10+)
- [Docker Compose](https://docs.docker.com/compose/install/) (v2.0+)

### Launch

```bash
# Clone the repository
git clone https://github.com/your-org/radar.git
cd radar

# Download reference databases (first time only)
chmod +x databases/download_dbs.sh
./databases/download_dbs.sh

# Start all services
docker compose up -d

# Verify everything is running
docker compose ps
```

The application will be available at:

| Service   | URL                        |
|-----------|----------------------------|
| Frontend  | http://localhost:3000       |
| API       | http://localhost:8000       |
| API Docs  | http://localhost:8000/docs  |

### First Steps

1. Open http://localhost:3000 in your browser.
2. Create a new project and provide a name and description.
3. Upload FASTQ files (paired-end Illumina or long-read Oxford Nanopore).
4. Select the analysis modules you want to run.
5. Monitor progress on the dashboard and explore results when complete.

## Architecture

```
                    +----------------+
                    |   Frontend     |
                    |  (Next.js)     |
                    +-------+--------+
                            |
                            v
                    +-------+--------+
                    |   Backend API  |
                    |   (FastAPI)    |
                    +---+--------+---+
                        |        |
               +--------+        +--------+
               v                          v
       +-------+--------+       +--------+-------+
       |   PostgreSQL    |       |     Redis      |
       |   (metadata)    |       |  (task queue)  |
       +----------------+        +-------+--------+
                                         |
                                         v
                                 +-------+--------+
                                 |  Celery Worker |
                                 |  (analysis)    |
                                 +----------------+
```

- **Frontend**: Next.js React application with interactive data visualizations (D3.js, Recharts).
- **Backend API**: FastAPI service handling authentication, project/sample management, file uploads, and result retrieval.
- **Worker**: Celery workers executing bioinformatics pipelines (AMRFinderPlus, ABRicate, MOB-suite, custom scripts).
- **PostgreSQL**: Relational store for projects, samples, analysis results, and user data.
- **Redis**: Message broker for Celery task queue and result caching.

## Tech Stack

| Layer       | Technology                                      |
|-------------|------------------------------------------------|
| Frontend    | Next.js 14, React 18, TypeScript, Tailwind CSS |
| Backend     | Python 3.12, FastAPI, SQLAlchemy, Pydantic      |
| Task Queue  | Celery 5, Redis 7                               |
| Database    | PostgreSQL 16                                   |
| Bioinfo     | AMRFinderPlus, ABRicate, MOB-suite, Prokka      |
| Containers  | Docker, Docker Compose                          |
| Testing     | pytest, httpx, Jest, React Testing Library       |

## Screenshots

*Screenshots will be added after the initial UI is finalized.*

## Development

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Running Tests

```bash
# Backend tests
cd backend
pytest ../tests/ -v

# Frontend tests
cd frontend
npm test
```

### Code Style

- Python: Ruff for linting and formatting.
- TypeScript: ESLint + Prettier.

## Contributing

Contributions are welcome. Please open an issue to discuss proposed changes before submitting a pull request.

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/my-feature`).
3. Commit your changes.
4. Push to the branch and open a pull request.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Citation

If you use RADAR in your research, please cite:

```
RADAR: Resistome Analysis, Detection, and Assessment Resource.
[Citation details to be added upon publication.]
```
