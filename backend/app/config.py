from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://radar:radar@db:5432/radar"
    REDIS_URL: str = "redis://redis:6379/0"
    UPLOAD_DIR: str = "/data/uploads"
    RESULTS_DIR: str = "/data/results"
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024 * 1024  # 10GB
    ALLOWED_EXTENSIONS: List[str] = [
        ".fastq",
        ".fastq.gz",
        ".fq",
        ".fq.gz",
        ".fasta",
        ".fa",
        ".fna",
    ]

    model_config = {"env_prefix": "RADAR_"}


settings = Settings()
