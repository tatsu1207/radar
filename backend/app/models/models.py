import uuid
import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Text,
    Float,
    Integer,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Enum,
    JSON,
)
from sqlalchemy import Uuid as UUID
from sqlalchemy.orm import relationship

from app.db import Base


class InputType(str, enum.Enum):
    fastq = "fastq"
    fasta = "fasta"


class SampleStatus(str, enum.Enum):
    pending = "pending"
    qc = "qc"
    assembling = "assembling"
    annotating = "annotating"
    complete = "complete"
    failed = "failed"


class SequencingPlatform(str, enum.Enum):
    illumina = "illumina"
    ont = "ont"
    pacbio = "pacbio"


class FileSource(str, enum.Enum):
    upload = "upload"
    sra = "sra"
    bvbrc = "bvbrc"


class SRADownloadStatus(str, enum.Enum):
    queued = "queued"
    downloading = "downloading"
    complete = "complete"
    failed = "failed"


class PairType(str, enum.Enum):
    R1 = "R1"
    R2 = "R2"
    single = "single"
    assembly = "assembly"
    long_read = "long_read"


class SIR(str, enum.Enum):
    S = "S"
    I = "I"
    R = "R"


class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    complete = "complete"
    failed = "failed"
    cancelled = "cancelled"


class RiskCategory(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    samples = relationship("Sample", back_populates="project", cascade="all, delete-orphan")


class Sample(Base):
    __tablename__ = "samples"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    input_type = Column(Enum(InputType), nullable=False, default=InputType.fastq)
    status = Column(Enum(SampleStatus), nullable=False, default=SampleStatus.pending)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="samples")
    files = relationship("SampleFile", back_populates="sample", cascade="all, delete-orphan")
    metadata_record = relationship("Metadata", back_populates="sample", uselist=False, cascade="all, delete-orphan")
    ast_results = relationship("ASTResult", back_populates="sample", cascade="all, delete-orphan")
    analysis_jobs = relationship("AnalysisJob", back_populates="sample", cascade="all, delete-orphan")
    arg_results = relationship("ARGResult", back_populates="sample", cascade="all, delete-orphan")
    plasmid_results = relationship("PlasmidResult", back_populates="sample", cascade="all, delete-orphan")
    mobility_results = relationship("MobilityResult", back_populates="sample", cascade="all, delete-orphan")
    risk_score = relationship("RiskScore", back_populates="sample", uselist=False, cascade="all, delete-orphan")
    virulence_results = relationship("VirulenceResult", back_populates="sample", cascade="all, delete-orphan")


class SampleFile(Base):
    __tablename__ = "sample_files"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False)
    file_path = Column(String(1024), nullable=False)
    file_type = Column(String(50), nullable=True)
    pair = Column(Enum(PairType), nullable=False, default=PairType.single)
    platform = Column(Enum(SequencingPlatform), nullable=True)
    source = Column(Enum(FileSource), nullable=False, default=FileSource.upload)
    original_filename = Column(String(512), nullable=True)
    file_size = Column(BigInteger, nullable=True)

    sample = relationship("Sample", back_populates="files")


class Metadata(Base):
    __tablename__ = "metadata"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False, unique=True)
    source = Column(String(255), nullable=True)
    collection_date = Column(DateTime, nullable=True)
    location = Column(String(255), nullable=True)
    species = Column(String(255), nullable=True)
    custom_json = Column(JSON, nullable=True)

    sample = relationship("Sample", back_populates="metadata_record")


class ASTResult(Base):
    __tablename__ = "ast_results"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False)
    antibiotic = Column(String(255), nullable=False)
    method = Column(String(255), nullable=True)
    mic = Column(String(50), nullable=True)
    sir = Column(Enum(SIR), nullable=False)

    sample = relationship("Sample", back_populates="ast_results")


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False)
    tool = Column(String(255), nullable=False)
    status = Column(Enum(JobStatus), nullable=False, default=JobStatus.pending)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    log = Column(Text, nullable=True)
    celery_task_id = Column(String(255), nullable=True)
    threads = Column(Integer, nullable=True, default=4)

    sample = relationship("Sample", back_populates="analysis_jobs")


class ARGResult(Base):
    __tablename__ = "arg_results"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False)
    gene = Column(String(255), nullable=False)
    drug_class = Column(String(255), nullable=True)
    mechanism = Column(String(255), nullable=True)
    identity = Column(Float, nullable=True)
    coverage = Column(Float, nullable=True)
    contig = Column(String(255), nullable=True)
    start = Column(Integer, nullable=True)
    end = Column(Integer, nullable=True)
    database = Column(String(100), nullable=True)
    on_plasmid = Column(Boolean, default=False)

    sample = relationship("Sample", back_populates="arg_results")


class PlasmidResult(Base):
    __tablename__ = "plasmid_results"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False)
    plasmid_id = Column(String(255), nullable=True)
    mob_type = Column(String(255), nullable=True)
    replicon = Column(String(255), nullable=True)
    predicted_transferability = Column(Boolean, default=False)

    sample = relationship("Sample", back_populates="plasmid_results")


class MobilityResult(Base):
    __tablename__ = "mobility_results"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False)
    element_type = Column(String(255), nullable=False)
    family = Column(String(255), nullable=True)
    contig = Column(String(255), nullable=True)
    start = Column(Integer, nullable=True)
    end = Column(Integer, nullable=True)
    nearby_args = Column(JSON, nullable=True)

    sample = relationship("Sample", back_populates="mobility_results")


class RiskScore(Base):
    __tablename__ = "risk_scores"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False, unique=True)
    arg_score = Column(Float, nullable=False, default=0.0)
    vf_score = Column(Float, nullable=False, default=0.0)
    mobility_score = Column(Float, nullable=False, default=0.0)
    composite_score = Column(Float, nullable=False, default=0.0)
    risk_category = Column(Enum(RiskCategory), nullable=False, default=RiskCategory.low)

    sample = relationship("Sample", back_populates="risk_score")


class VirulenceResult(Base):
    __tablename__ = "virulence_results"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False)
    gene = Column(String(255), nullable=False)
    category = Column(String(255), nullable=True)
    identity = Column(Float, nullable=True)
    coverage = Column(Float, nullable=True)
    contig = Column(String(255), nullable=True)
    database = Column(String(100), nullable=True)

    sample = relationship("Sample", back_populates="virulence_results")


class SRADownload(Base):
    __tablename__ = "sra_downloads"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="SET NULL"), nullable=True)
    srr_accession = Column(String(20), nullable=False)
    status = Column(Enum(SRADownloadStatus), nullable=False, default=SRADownloadStatus.queued)
    progress = Column(Float, default=0.0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)


class BVBRCFetch(Base):
    __tablename__ = "bvbrc_fetches"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="SET NULL"), nullable=True)
    genome_id = Column(String(50), nullable=False)
    status = Column(Enum(SRADownloadStatus), nullable=False, default=SRADownloadStatus.queued)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
