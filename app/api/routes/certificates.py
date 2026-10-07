"""Single-certificate retrieval (PDF download)."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.certificate import CERT_FAILED, CERT_SUCCESS
from app.services import job_service
from app.services.storage_service import get_certificate_path

router = APIRouter(prefix="/certificates", tags=["certificates"])


@router.get(
    "/{certificate_id}",
    summary="Download a generated certificate PDF",
    description="Returns the PDF for SUCCESS certificates; 404 for unknown ids or "
    "missing files; 422 when generation failed or the certificate is not ready yet.",
    responses={
        200: {"description": "PDF file"},
        404: {"description": "Certificate not found"},
        422: {"description": "Certificate generation failed for this recipient"},
    },
)
def download_certificate(certificate_id: str, db: Session = Depends(get_db)):
    cert = job_service.get_certificate_by_identifier(db, certificate_id)
    if cert is None:
        raise HTTPException(status_code=404, detail="Certificate not found")
    if cert.status == CERT_FAILED:
        raise HTTPException(
            status_code=422,
            detail=f"Certificate generation failed: {cert.error_message or 'unknown error'}",
        )
    if cert.status != CERT_SUCCESS or not cert.file_path:
        raise HTTPException(
            status_code=422,
            detail=f"Certificate is not ready (status={cert.status})",
        )
    path = get_certificate_path(cert.file_path)
    if path is None:
        raise HTTPException(status_code=404, detail="Certificate file not found")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"{certificate_id}.pdf",
    )
