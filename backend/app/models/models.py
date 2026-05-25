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
    prophage_results = relationship("ProphageResult", back_populates="sample", cascade="all, delete-orphan")
    species_result = relationship("SpeciesResult", back_populates="sample", uselist=False, cascade="all, delete-orphan")
    mlst_result = relationship("MLSTResult", back_populates="sample", uselist=False, cascade="all, delete-orphan")
    bakta_annotation = relationship("BaktaAnnotation", back_populates="sample", uselist=False, cascade="all, delete-orphan")
    resfinder_results = relationship("ResFinderResult", back_populates="sample", cascade="all, delete-orphan")
    rgi_results = relationship("RGIResult", back_populates="sample", cascade="all, delete-orphan")
    vfdb_results = relationship("VFDBResult", back_populates="sample", cascade="all, delete-orphan")
    serotype_result = relationship("SerotypeResult", back_populates="sample", uselist=False, cascade="all, delete-orphan")
    cgmlst_result = relationship("CgMLSTResult", back_populates="sample", uselist=False, cascade="all, delete-orphan")
    integron_results = relationship("IntegronResult", back_populates="sample", cascade="all, delete-orphan")
    point_mutation_results = relationship("PointMutationResult", back_populates="sample", cascade="all, delete-orphan")
    crispr_results = relationship("CRISPRResult", back_populates="sample", cascade="all, delete-orphan")
    defensefinder_results = relationship("DefenseFinderResult", back_populates="sample", cascade="all, delete-orphan")
    ice_results = relationship("ICEResult", back_populates="sample", cascade="all, delete-orphan")
    bacmet_results = relationship("BacMetResult", back_populates="sample", cascade="all, delete-orphan")
    ml_predictions = relationship("MLPhenotypePrediction", back_populates="sample", cascade="all, delete-orphan")


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
    on_prophage = Column(Boolean, default=False)
    contig_type = Column(String(50), nullable=True)  # chromosome, plasmid, prophage
    # Operon context
    operon_size = Column(Integer, nullable=True)
    operon_position = Column(Integer, nullable=True)
    # Gene dosage
    gene_copies = Column(Integer, nullable=True)
    # Codon adaptation index
    cai = Column(Float, nullable=True)
    rare_codon_pct = Column(Float, nullable=True)
    rare_codon_clusters = Column(Integer, nullable=True)
    # GC content
    gene_gc = Column(Float, nullable=True)
    genome_gc = Column(Float, nullable=True)
    gc_deviation = Column(Float, nullable=True)
    # sRNA proximity
    nearest_srna = Column(String(255), nullable=True)
    nearest_srna_distance = Column(Integer, nullable=True)
    # Integron context
    in_integron = Column(Boolean, default=False)
    nearest_integron_distance = Column(Integer, nullable=True)
    nearest_integron_type = Column(String(50), nullable=True)
    # Point mutations
    point_mutations = Column(String(1024), nullable=True)

    sample = relationship("Sample", back_populates="arg_results")
    promoter_result = relationship("PromoterResult", back_populates="arg_result", uselist=False, cascade="all, delete-orphan")
    rbs_result = relationship("RBSResult", back_populates="arg_result", uselist=False, cascade="all, delete-orphan")


class PromoterResult(Base):
    __tablename__ = "promoter_results"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    arg_result_id = Column(UUID, ForeignKey("arg_results.id", ondelete="CASCADE"), nullable=False, unique=True)
    ldf_score = Column(Float, nullable=True)
    tf_binding_sites = Column(Integer, nullable=True)
    promoter_distance = Column(Integer, nullable=True)
    up_element_at_ratio = Column(Float, nullable=True)

    arg_result = relationship("ARGResult", back_populates="promoter_result")


class RBSResult(Base):
    __tablename__ = "rbs_results"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    arg_result_id = Column(UUID, ForeignKey("arg_results.id", ondelete="CASCADE"), nullable=False, unique=True)
    expression = Column(Float, nullable=True)
    dg_total = Column(Float, nullable=True)
    dg_mrna = Column(Float, nullable=True)

    arg_result = relationship("ARGResult", back_populates="rbs_result")


class PlasmidResult(Base):
    __tablename__ = "plasmid_results"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False)
    plasmid_id = Column(String(255), nullable=True)
    mob_type = Column(String(255), nullable=True)
    replicon = Column(String(255), nullable=True)
    predicted_transferability = Column(Boolean, default=False)
    predicted_mobility = Column(String(50), nullable=True)  # conjugative, mobilizable, non-mobilizable

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


class ProphageResult(Base):
    __tablename__ = "prophage_results"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False)
    contig = Column(String(255), nullable=True)
    start = Column(Integer, nullable=True)
    end = Column(Integer, nullable=True)
    length = Column(Integer, nullable=True)
    virus_score = Column(Float, nullable=True)
    taxonomy = Column(String(512), nullable=True)
    n_hallmarks = Column(Integer, nullable=True)
    nearby_args = Column(JSON, nullable=True)

    sample = relationship("Sample", back_populates="prophage_results")


class SpeciesResult(Base):
    __tablename__ = "species_results"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False, unique=True)
    species = Column(String(255), nullable=True)
    identity = Column(Float, nullable=True)
    alignment_length = Column(Integer, nullable=True)
    accession = Column(String(100), nullable=True)
    method = Column(String(50), nullable=True)  # blast_16s, skani, gtdbtk
    top_hits = Column(JSON, nullable=True)  # list of top N hits

    sample = relationship("Sample", back_populates="species_result")


class MLSTResult(Base):
    __tablename__ = "mlst_results"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False, unique=True)
    scheme = Column(String(100), nullable=True)
    sequence_type = Column(String(50), nullable=True)
    alleles = Column(JSON, nullable=True)

    sample = relationship("Sample", back_populates="mlst_result")


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
    start = Column(Integer, nullable=True)
    end = Column(Integer, nullable=True)
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


# ---------------------------------------------------------------------------
# New models for comparative genomics pipeline
# ---------------------------------------------------------------------------

class BaktaAnnotation(Base):
    """Bakta genome annotation summary for a sample."""
    __tablename__ = "bakta_annotations"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False, unique=True)
    gff_path = Column(String(1024), nullable=True)
    gbk_path = Column(String(1024), nullable=True)
    faa_path = Column(String(1024), nullable=True)
    cds_count = Column(Integer, nullable=True)
    rrna_count = Column(Integer, nullable=True)
    trna_count = Column(Integer, nullable=True)
    ncrna_count = Column(Integer, nullable=True)
    crispr_count = Column(Integer, nullable=True)
    hypothetical_count = Column(Integer, nullable=True)

    sample = relationship("Sample", back_populates="bakta_annotation")


class ResFinderResult(Base):
    """Resistance gene hit from ResFinder database."""
    __tablename__ = "resfinder_results"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False)
    gene = Column(String(255), nullable=False)
    drug_class = Column(String(255), nullable=True)
    phenotype = Column(String(512), nullable=True)
    identity = Column(Float, nullable=True)
    coverage = Column(Float, nullable=True)
    contig = Column(String(255), nullable=True)
    start = Column(Integer, nullable=True)
    end = Column(Integer, nullable=True)
    accession = Column(String(100), nullable=True)

    sample = relationship("Sample", back_populates="resfinder_results")


class RGIResult(Base):
    """Resistance gene hit from CARD via RGI."""
    __tablename__ = "rgi_results"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False)
    gene = Column(String(255), nullable=False)
    drug_class = Column(Text, nullable=True)
    resistance_mechanism = Column(Text, nullable=True)
    amr_gene_family = Column(Text, nullable=True)
    model_type = Column(String(100), nullable=True)  # protein homolog, variant, overexpression, etc.
    identity = Column(Float, nullable=True)
    coverage = Column(Float, nullable=True)
    contig = Column(Text, nullable=True)
    start = Column(Integer, nullable=True)
    end = Column(Integer, nullable=True)
    cut_off = Column(String(50), nullable=True)  # strict, perfect, loose

    sample = relationship("Sample", back_populates="rgi_results")


class VFDBResult(Base):
    """Virulence factor hit from VFDB via ABRicate."""
    __tablename__ = "vfdb_results"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False)
    gene = Column(String(255), nullable=False)
    product = Column(String(512), nullable=True)
    vf_class = Column(String(255), nullable=True)
    identity = Column(Float, nullable=True)
    coverage = Column(Float, nullable=True)
    contig = Column(String(255), nullable=True)
    start = Column(Integer, nullable=True)
    end = Column(Integer, nullable=True)
    accession = Column(String(100), nullable=True)

    sample = relationship("Sample", back_populates="vfdb_results")


class SerotypeResult(Base):
    """In silico serotyping result."""
    __tablename__ = "serotype_results"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False, unique=True)
    tool = Column(String(100), nullable=True)  # serotypefinder, sistr, kleborate
    serotype = Column(String(255), nullable=True)
    o_antigen = Column(String(100), nullable=True)
    h_antigen = Column(String(100), nullable=True)
    k_locus = Column(String(100), nullable=True)
    serovar = Column(String(255), nullable=True)  # for Salmonella (SISTR)
    details = Column(JSON, nullable=True)  # tool-specific extra fields

    sample = relationship("Sample", back_populates="serotype_result")


class CgMLSTResult(Base):
    """Core-genome MLST result from chewBBACA."""
    __tablename__ = "cgmlst_results"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False, unique=True)
    schema_name = Column(String(255), nullable=True)
    allelic_profile = Column(JSON, nullable=True)  # {locus: allele_id, ...}
    loci_found = Column(Integer, nullable=True)
    loci_total = Column(Integer, nullable=True)

    sample = relationship("Sample", back_populates="cgmlst_result")


class IntegronResult(Base):
    """Integron detected by IntegronFinder."""
    __tablename__ = "integron_results"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False)
    integron_id = Column(String(100), nullable=True)
    integron_type = Column(String(50), nullable=True)  # complete, In0, CALIN
    contig = Column(String(255), nullable=True)
    start = Column(Integer, nullable=True)
    end = Column(Integer, nullable=True)
    cassettes = Column(JSON, nullable=True)  # list of gene cassettes

    sample = relationship("Sample", back_populates="integron_results")


class PointMutationResult(Base):
    """Resistance-associated point mutation from PointFinder."""
    __tablename__ = "point_mutation_results"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False)
    gene = Column(String(255), nullable=False)
    mutation = Column(String(100), nullable=False)  # e.g., S83L
    drug_class = Column(String(255), nullable=True)
    resistance = Column(String(512), nullable=True)
    nucleotide_change = Column(String(100), nullable=True)

    sample = relationship("Sample", back_populates="point_mutation_results")


class CRISPRResult(Base):
    """CRISPR array detected by CRISPRCasFinder."""
    __tablename__ = "crispr_results"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False)
    crispr_id = Column(String(100), nullable=True)
    contig = Column(String(255), nullable=True)
    start = Column(Integer, nullable=True)
    end = Column(Integer, nullable=True)
    cas_type = Column(String(100), nullable=True)  # e.g., Type I-E, Type II-A
    cas_genes = Column(JSON, nullable=True)  # list of cas gene names
    num_spacers = Column(Integer, nullable=True)
    repeat_length = Column(Integer, nullable=True)
    spacer_length = Column(Integer, nullable=True)
    evidence_level = Column(Integer, nullable=True)  # CRISPRCasFinder evidence level 1-4

    sample = relationship("Sample", back_populates="crispr_results")


class DefenseFinderResult(Base):
    """Defense system detected by DefenseFinder."""
    __tablename__ = "defensefinder_results"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False)
    system_type = Column(String(100), nullable=False)  # RM, Abi, BREX, DISARM, etc.
    subtype = Column(String(100), nullable=True)  # e.g., Type I RM, Type II RM
    genes = Column(JSON, nullable=True)  # list of gene names in the system
    contig = Column(String(255), nullable=True)
    start = Column(Integer, nullable=True)
    end = Column(Integer, nullable=True)
    protein_count = Column(Integer, nullable=True)

    sample = relationship("Sample", back_populates="defensefinder_results")


class ICEResult(Base):
    """Integrative and conjugative element detected by ICEfinder."""
    __tablename__ = "ice_results"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False)
    ice_id = Column(String(100), nullable=True)
    ice_type = Column(String(100), nullable=True)  # ICE, IME, CIME, AICE
    contig = Column(String(255), nullable=True)
    start = Column(Integer, nullable=True)
    end = Column(Integer, nullable=True)
    length = Column(Integer, nullable=True)
    integrase = Column(String(255), nullable=True)
    arg_genes = Column(JSON, nullable=True)  # ARGs carried on ICE
    nearest_trna = Column(String(100), nullable=True)

    sample = relationship("Sample", back_populates="ice_results")




class BacMetResult(Base):
    """BacMet2 biocide and metal resistance gene detection."""
    __tablename__ = "bacmet_results"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False)
    gene = Column(String(255), nullable=False)
    bacmet_id = Column(String(50), nullable=True)
    compound = Column(String(512), nullable=True)  # e.g. "Arsenic (As)", "Copper (Cu)"
    identity = Column(Float, nullable=True)
    coverage = Column(Float, nullable=True)
    contig = Column(String(255), nullable=True)
    start = Column(Integer, nullable=True)
    end = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    sample = relationship("Sample", back_populates="bacmet_results")


class MLPhenotypePrediction(Base):
    """ML-based per-antibiotic phenotype prediction from pre-trained RF models."""
    __tablename__ = "ml_phenotype_predictions"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID, ForeignKey("samples.id", ondelete="CASCADE"), nullable=False)
    antibiotic = Column(String(255), nullable=False)
    drug_class = Column(String(255), nullable=True)
    prediction = Column(String(20), nullable=False)  # "Resistant" or "Susceptible"
    probability = Column(Float, nullable=False)
    confidence = Column(String(20), nullable=False)  # "High", "Moderate", "Low"
    key_genes = Column(JSON, nullable=True)
    key_mutations = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    sample = relationship("Sample", back_populates="ml_predictions")


