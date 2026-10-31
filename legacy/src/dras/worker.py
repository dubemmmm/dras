from celery import Celery

from dras.config import get_settings
from dras.db import SessionLocal
from dras.service import AssessmentService

settings = get_settings()
celery_app = Celery("dras", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_track_started=True, task_acks_late=True, worker_prefetch_multiplier=1)


@celery_app.task(bind=True, autoretry_for=(OSError,), retry_backoff=True, max_retries=3)
def extract_assessment(self, assessment_id: str, owner_email: str, expected_version: int) -> dict:
    self.update_state(state="PROGRESS", meta={"stage": "extracting", "percent": 10})
    with SessionLocal() as db:
        result = AssessmentService(db, settings).extract(assessment_id, owner_email, expected_version)
    return {"assessment_id": assessment_id, "state": result.state, "version": result.version}

