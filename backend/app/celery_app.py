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
)

# Import tasks so they are registered with the Celery app
celery_app.conf.imports = ["app.core.pipeline", "app.core.sra", "app.core.bvbrc"]
