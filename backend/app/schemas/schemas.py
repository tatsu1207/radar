import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Project ──────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ProjectRead(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectList(BaseModel):
    items: List[ProjectRead]
    total: int
    page: int = 1
    size: int = 50


# ── Sample ───────────────────────────────────────────────────────────────────

class SampleCreate(BaseModel):
    name: str
    input_type: str = "fastq"


class SampleUpdate(BaseModel):
    name: Optional[str] = None
    input_type: Optional[str] = None


class SampleFileRead(BaseModel):
    id: uuid.UUID
    file_path: str
    file_type: Optional[str] = None
    pair: str

    model_config = {"from_attributes": True}


class SampleRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    input_type: str
    status: str
    created_at: datetime
    updated_at: datetime
    files: List[SampleFileRead] = []

    model_config = {"from_attributes": True}


class SampleList(BaseModel):
    items: List[SampleRead]
    total: int
    page: int = 1
    size: int = 50


# ── Metadata ─────────────────────────────────────────────────────────────────

class MetadataCreate(BaseModel):
    source: Optional[str] = None
    collection_date: Optional[datetime] = None
    location: Optional[str] = None
    species: Optional[str] = None
    custom_json: Optional[Dict[str, Any]] = None


class MetadataRead(BaseModel):
    id: uuid.UUID
    sample_id: uuid.UUID
    source: Optional[str] = None
    collection_date: Optional[datetime] = None
    location: Optional[str] = None
    species: Optional[str] = None
    custom_json: Optional[Dict[str, Any]] = None

    model_config = {"from_attributes": True}


class MetadataUpdate(BaseModel):
    source: Optional[str] = None
    collection_date: Optional[datetime] = None
    location: Optional[str] = None
    species: Optional[str] = None
    custom_json: Optional[Dict[str, Any]] = None


# ── AST ──────────────────────────────────────────────────────────────────────

class ASTResultCreate(BaseModel):
    antibiotic: str
    method: Optional[str] = None
    mic: Optional[str] = None
    sir: str


class ASTResultRead(BaseModel):
    id: uuid.UUID
    sample_id: uuid.UUID
    antibiotic: str
    method: Optional[str] = None
    mic: Optional[str] = None
    sir: str

    model_config = {"from_attributes": True}


class ASTResultUpdate(BaseModel):
    antibiotic: Optional[str] = None
    method: Optional[str] = None
    mic: Optional[str] = None
    sir: Optional[str] = None


# ── ARGResult ────────────────────────────────────────────────────────────────

class ARGResultRead(BaseModel):
    id: uuid.UUID
    sample_id: uuid.UUID
    gene: str
    drug_class: Optional[str] = None
    mechanism: Optional[str] = None
    identity: Optional[float] = None
    coverage: Optional[float] = None
    contig: Optional[str] = None
    start: Optional[int] = None
    end: Optional[int] = None
    database: Optional[str] = None
    on_plasmid: bool = False

    model_config = {"from_attributes": True}


# ── PlasmidResult ────────────────────────────────────────────────────────────

class PlasmidResultRead(BaseModel):
    id: uuid.UUID
    sample_id: uuid.UUID
    plasmid_id: Optional[str] = None
    mob_type: Optional[str] = None
    replicon: Optional[str] = None
    predicted_transferability: bool = False

    model_config = {"from_attributes": True}


# ── MobilityResult ───────────────────────────────────────────────────────────

class MobilityResultRead(BaseModel):
    id: uuid.UUID
    sample_id: uuid.UUID
    element_type: str
    family: Optional[str] = None
    contig: Optional[str] = None
    start: Optional[int] = None
    end: Optional[int] = None
    nearby_args: Optional[List[Dict[str, Any]]] = None

    model_config = {"from_attributes": True}


# ── RiskScore ────────────────────────────────────────────────────────────────

class RiskScoreRead(BaseModel):
    id: uuid.UUID
    sample_id: uuid.UUID
    arg_score: float
    vf_score: float
    mobility_score: float
    composite_score: float
    risk_category: str

    model_config = {"from_attributes": True}


# ── VirulenceResult ──────────────────────────────────────────────────────────

class VirulenceResultRead(BaseModel):
    id: uuid.UUID
    sample_id: uuid.UUID
    gene: str
    description: Optional[str] = None
    category: Optional[str] = None
    identity: Optional[float] = None
    coverage: Optional[float] = None
    contig: Optional[str] = None
    database: Optional[str] = None

    model_config = {"from_attributes": True}


# ── AnalysisJob ──────────────────────────────────────────────────────────────

class AnalysisJobRead(BaseModel):
    id: uuid.UUID
    sample_id: uuid.UUID
    tool: str
    status: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    log: Optional[str] = None
    celery_task_id: Optional[str] = None
    threads: Optional[int] = None

    model_config = {"from_attributes": True}


# ── File Upload ──────────────────────────────────────────────────────────────

class FileUploadResponse(BaseModel):
    sample_id: uuid.UUID
    files: List[SampleFileRead]
    message: str


# ── Analysis Request ─────────────────────────────────────────────────────────

class AnalysisRequest(BaseModel):
    threads: int = Field(default=4, ge=1, le=128)


# ── Risk Weights ─────────────────────────────────────────────────────────────

class RiskWeights(BaseModel):
    arg_weight: float = 1.0 / 3.0
    vf_weight: float = 1.0 / 3.0
    mobility_weight: float = 1.0 / 3.0


# ── Phenotype Comparison ────────────────────────────────────────────────────

class PhenotypeComparison(BaseModel):
    antibiotic: str
    predicted: Optional[str] = None
    observed: Optional[str] = None
    concordant: bool = False


# ── File Manager ────────────────────────────────────────────────────────────

class FileSlot(BaseModel):
    id: Optional[uuid.UUID] = None
    filename: Optional[str] = None
    size: Optional[int] = None


class FileManagerSample(BaseModel):
    sample_id: uuid.UUID
    name: str
    status: str
    input_type: str = "fastq"
    illumina_r1: Optional[FileSlot] = None
    illumina_r2: Optional[FileSlot] = None
    long_read: Optional[FileSlot] = None
    long_read_platform: Optional[str] = None
    assembly: Optional[FileSlot] = None
    source: str = "upload"
    has_metadata: bool = False
    project_id: Optional[uuid.UUID] = None
    project_name: Optional[str] = None
    pipeline_status: Optional[str] = None  # not_started, running, complete, failed
    pipeline_job_id: Optional[str] = None
    pipeline_progress: int = 0  # 0-100
    busco_complete: Optional[float] = None  # BUSCO completeness %


class FileManagerResponse(BaseModel):
    samples: List[FileManagerSample]
    total: int


class ServerPathRequest(BaseModel):
    paths: List[str]


class SRARequest(BaseModel):
    accessions: List[str] = []
    groups: Optional[List[List[str]]] = None  # grouped accessions: each inner list = one sample


class SRADownloadRead(BaseModel):
    id: uuid.UUID
    srr_accession: str
    sample_id: Optional[uuid.UUID] = None
    status: str
    progress: float = 0.0
    error_message: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class BVBRCRequest(BaseModel):
    genome_ids: List[str]


class BVBRCFetchRead(BaseModel):
    id: uuid.UUID
    genome_id: str
    sample_id: Optional[uuid.UUID] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class MetadataTSVRow(BaseModel):
    sample_id: str
    matched: bool = False
    fields: Dict[str, Any] = {}


class MetadataTSVPreview(BaseModel):
    rows: List[MetadataTSVRow]
    matched: int
    unmatched: int


class MetadataTSVResult(BaseModel):
    updated: int
    created: int
    errors: List[str] = []
