"""Background worker: processes one job, isolating per-certificate failures.

Each certificate runs in its own try/except and is committed individually,
so one failure never stops the rest of the job and no giant transaction is
held. Job counters are updated in the same commit as the certificate row.
"""

from sqlalchemy import select

from app.core.logging import logger
from app.db import database
from app.db.models.certificate import (
    CERT_FAILED,
    CERT_PENDING,
    CERT_PROCESSING,
    CERT_SUCCESS,
    Certificate,
)
from app.db.models.generation_job import (
    JOB_COMPLETED,
    JOB_COMPLETED_WITH_ERRORS,
    JOB_FAILED,
    JOB_PROCESSING,
    JOB_QUEUED,
    GenerationJob,
)
from app.services import certificate_service, storage_service
from app.services.job_service import now_utc


def process_job(job_id: str) -> None:
    """Run a whole job to a terminal state. Never raises to the caller."""
    db = database.SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if job is None:
            logger.error("job not found job_id=%s", job_id)
            return
        if job.status != JOB_QUEUED:
            # Single-claim: only a QUEUED job may be processed. This makes a
            # duplicate dispatch (or manual re-run) a no-op instead of
            # double-counting counters. Interrupted PROCESSING jobs are marked
            # FAILED at startup, never silently resumed.
            logger.info("job not claimable job_id=%s status=%s", job_id, job.status)
            return
        job.status = JOB_PROCESSING
        if job.started_at is None:
            job.started_at = now_utc()
        db.commit()
        logger.info("job started job_id=%s total=%d", job_id, job.total_count)

        pending = list(
            db.scalars(
                select(Certificate)
                .where(
                    Certificate.job_id == job_id,
                    Certificate.status.in_([CERT_PENDING, CERT_PROCESSING]),
                )
                .order_by(Certificate.id)
            ).all()
        )
        for cert in pending:
            _process_one(db, job, cert)

        db.refresh(job)
        if job.failure_count > 0:
            job.status = JOB_COMPLETED_WITH_ERRORS
        else:
            job.status = JOB_COMPLETED
        job.completed_at = now_utc()
        db.commit()
        logger.info(
            "job completed job_id=%s status=%s success=%d failure=%d",
            job_id,
            job.status,
            job.success_count,
            job.failure_count,
        )
    except Exception as exc:  # job-level failure only
        logger.exception("job failed job_id=%s error=%s", job_id, exc)
        try:
            job = db.get(GenerationJob, job_id)
            if job is not None and job.status not in (JOB_COMPLETED, JOB_COMPLETED_WITH_ERRORS):
                job.status = JOB_FAILED
                job.completed_at = now_utc()
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


def _process_one(db, job, cert) -> None:
    """Process one certificate. Never raises: a DB error here must not abort
    the remaining recipients (that would turn one bad row into a dead job)."""
    cert_id = cert.certificate_identifier
    job_pk = job.id  # plain str: safe to log even after expire()
    logger.info("certificate started job_id=%s certificate_id=%s", job_pk, cert_id)
    try:
        cert.status = CERT_PROCESSING
        db.commit()

        pdf = certificate_service.render_certificate_pdf(
            recipient_name=cert.recipient_name,
            event_name=job.event_name,
            event_date=job.event_date.isoformat(),
            issuer_name=job.issuer_name,
            certificate_id=cert_id,
        )
        stored = storage_service.save_certificate(job.id, cert_id, pdf)

        cert.status = CERT_SUCCESS
        cert.file_path = stored
        cert.error_message = None
        job.success_count += 1
        logger.info("certificate succeeded job_id=%s certificate_id=%s", job.id, cert_id)
    except Exception as exc:
        # Failure isolation: record and continue with the next certificate.
        db.rollback()
        cert.status = CERT_FAILED
        cert.error_message = f"{type(exc).__name__}: {exc}"[:2000]
        job.failure_count += 1
        logger.warning(
            "certificate failed job_id=%s certificate_id=%s error=%s", job.id, cert_id, exc
        )
    try:
        cert.completed_at = now_utc()
        job.processed_count += 1
        db.commit()
    except Exception as exc:
        # The commit itself failed: roll back so the session stays usable and
        # move on. Expire in-memory state first: without this, the incremented
        # Python-side counters would be persisted by the *next* commit even
        # though this recipient was rolled back. This recipient is left
        # uncounted rather than killing the job.
        db.rollback()
        db.expire(job)
        db.expire(cert)
        logger.error(
            "certificate result not persisted job_id=%s certificate_id=%s error=%s",
            job_pk,
            cert_id,
            exc,
        )
