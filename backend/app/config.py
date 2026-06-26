import secrets

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

    JWT_SECRET_KEY: str = secrets.token_urlsafe(32)
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 24 hours

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    BASE_URL: str = "http://localhost:3000"

    model_config = {"env_prefix": "RADAR_"}


settings = Settings()
