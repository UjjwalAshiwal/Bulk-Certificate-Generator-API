"""Certificate model (one row per recipient in a job)."""

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.db.models.generation_job import GenerationJob

CERT_PENDING = "PENDING"
CERT_PROCESSING = "PROCESSING"
CERT_SUCCESS = "SUCCESS"
CERT_FAILED = "FAILED"


class Certificate(Base):
    __tablename__ = "certificates"
    __table_args__ = (
        UniqueConstraint("job_id", "certificate_identifier", name="uq_cert_job_identifier"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "generation_jobs.id",
            name="fk_certificates_job_id_generation_jobs",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    recipient_name: Mapped[str] = mapped_column(String(200), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    # Globally unique (stricter than per-job) so GET /certificates/{id} is
    # unambiguous. The UNIQUE constraint carries the index; no separate one.
    # Documented in README.
    certificate_identifier: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=CERT_PENDING, index=True
    )
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.UTC)
    )
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped["GenerationJob"] = relationship("GenerationJob", back_populates="certificates")
