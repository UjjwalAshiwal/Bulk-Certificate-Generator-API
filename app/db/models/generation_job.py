"""GenerationJob model (one row per bulk request)."""

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.db.models.certificate import Certificate

JOB_QUEUED = "QUEUED"
JOB_PROCESSING = "PROCESSING"
JOB_COMPLETED = "COMPLETED"
JOB_COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
JOB_FAILED = "FAILED"
# FAILED = the job itself could not complete; COMPLETED_WITH_ERRORS = all
# items processed but at least one item failed.
JOB_STATUSES = {
    JOB_QUEUED,
    JOB_PROCESSING,
    JOB_COMPLETED,
    JOB_COMPLETED_WITH_ERRORS,
    JOB_FAILED,
}
JOB_TERMINAL = {JOB_COMPLETED, JOB_COMPLETED_WITH_ERRORS, JOB_FAILED}


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_name: Mapped[str] = mapped_column(String(255), nullable=False)
    event_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    issuer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=JOB_QUEUED, index=True)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.UTC)
    )
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    certificates: Mapped[list["Certificate"]] = relationship(
        "Certificate", back_populates="job", cascade="all, delete-orphan"
    )
