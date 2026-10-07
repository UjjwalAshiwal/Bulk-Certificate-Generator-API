"""Job creation + read helpers. No PDF or background logic here."""

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.db.models.certificate import CERT_PENDING, Certificate
from app.db.models.generation_job import JOB_QUEUED, GenerationJob
from app.schemas.jobs import GenerationJobCreate


class DuplicateCertificateIdError(ValueError):
    pass


def create_job(db: Session, payload: GenerationJobCreate) -> GenerationJob:
    """Validate, persist job + PENDING certificate rows, return the job."""
    job = GenerationJob(
        id=str(uuid.uuid4()),
        event_name=payload.event_name.strip(),
        event_date=payload.event_date,
        issuer_name=payload.issuer_name.strip(),
        status=JOB_QUEUED,
        total_count=len(payload.recipients),
    )
    db.add(job)
    db.flush()  # obtain job row before inserting children
    for r in payload.recipients:
        db.add(
            Certificate(
                job_id=job.id,
                recipient_name=r.name,
                recipient_email=r.email,
                certificate_identifier=r.certificate_id,
                status=CERT_PENDING,
            )
        )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # e.g. certificate_id already used by another job (global uniqueness).
        raise DuplicateCertificateIdError(
            "one or more certificate_id values are already in use"
        ) from exc
    db.refresh(job)
    logger.info("job created job_id=%s total=%d", job.id, job.total_count)
    return job


def get_job(db: Session, job_id: str) -> GenerationJob | None:
    return db.get(GenerationJob, job_id)


def get_job_certificates(db: Session, job_id: str) -> list[Certificate]:
    stmt = (
        select(Certificate)
        .where(Certificate.job_id == job_id)
        .order_by(Certificate.certificate_identifier)
    )
    return list(db.scalars(stmt).all())


def get_certificate_by_identifier(db: Session, certificate_id: str) -> Certificate | None:
    stmt = select(Certificate).where(Certificate.certificate_identifier == certificate_id)
    return db.scalars(stmt).first()


def progress_percentage(job: GenerationJob) -> float:
    """Derived, never stored: processed / total * 100 (0 when empty)."""
    if job.total_count <= 0:
        return 0.0
    return round(job.processed_count / job.total_count * 100, 1)


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)
