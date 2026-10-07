"""Job endpoints: create, status, per-certificate results."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.certificate import CERT_SUCCESS
from app.schemas.jobs import (
    GenerationJobCreate,
    GenerationJobResponse,
    JobCertificateItem,
    JobCertificatesResponse,
    JobStatusResponse,
)
from app.services import job_service
from app.services.job_service import DuplicateCertificateIdError
from app.workers.certificate_worker import process_job

router = APIRouter(prefix="/generation-jobs", tags=["generation-jobs"])


@router.post(
    "",
    response_model=GenerationJobResponse,
    status_code=202,
    summary="Create a bulk certificate-generation job",
    description="Validates recipients, persists a QUEUED job, and processes it in the background.",
)
def create_generation_job(
    payload: GenerationJobCreate, background: BackgroundTasks, db: Session = Depends(get_db)
):
    try:
        job = job_service.create_job(db, payload)
    except DuplicateCertificateIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background.add_task(process_job, job.id)
    return GenerationJobResponse(
        job_id=job.id,
        status=job.status,
        total_count=job.total_count,
        processed_count=job.processed_count,
        success_count=job.success_count,
        failure_count=job.failure_count,
        created_at=job.created_at,
    )


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    summary="Check job status and progress",
    description="Progress is derived as processed/total; counters stay consistent.",
)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = job_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Generation job not found")
    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        total_count=job.total_count,
        processed_count=job.processed_count,
        success_count=job.success_count,
        failure_count=job.failure_count,
        progress_percentage=job_service.progress_percentage(job),
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@router.get(
    "/{job_id}/certificates",
    response_model=JobCertificatesResponse,
    summary="List per-certificate results for a job",
    description="Shows SUCCESS/FAILED per recipient without exposing filesystem paths.",
)
def list_job_certificates(job_id: str, db: Session = Depends(get_db)):
    job = job_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Generation job not found")
    items = []
    for cert in job_service.get_job_certificates(db, job_id):
        items.append(
            JobCertificateItem(
                certificate_id=cert.certificate_identifier,
                recipient_name=cert.recipient_name,
                recipient_email=cert.recipient_email,
                status=cert.status,
                download_url=(
                    f"/api/v1/certificates/{cert.certificate_identifier}"
                    if cert.status == CERT_SUCCESS
                    else None
                ),
                error_message=cert.error_message,
            )
        )
    return JobCertificatesResponse(job_id=job.id, items=items)
