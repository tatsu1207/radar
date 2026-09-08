from celery import Celery
from app.config import settings

celery_app = Celery(
    "radar",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Route pipeline tasks to a dedicated queue with concurrency=1
    task_routes={
        "run_pipeline": {"queue": "pipeline"},
        "run_preprocessing": {"queue": "pipeline"},
        "run_annotation_only": {"queue": "pipeline"},
        "run_single_step": {"queue": "pipeline"},
    },
)

# Import tasks so they are registered with the Celery app
celery_app.conf.imports = ["app.core.pipeline", "app.core.sra", "app.core.bvbrc"]
