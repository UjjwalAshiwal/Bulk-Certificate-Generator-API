"""Pydantic schemas for generation jobs."""

import datetime as dt

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.config import settings


class RecipientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr = Field(max_length=320)
    certificate_id: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        return v

    @field_validator("certificate_id")
    @classmethod
    def cert_id_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("certificate_id must not be empty")
        return v


class GenerationJobCreate(BaseModel):
    event_name: str = Field(min_length=1, max_length=255)
    event_date: dt.date
    issuer_name: str = Field(min_length=1, max_length=255)
    recipients: list[RecipientCreate] = Field(min_length=1)

    @field_validator("event_name", "issuer_name")
    @classmethod
    def field_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @model_validator(mode="after")
    def check_duplicates_and_size(self):
        ids = [r.certificate_id for r in self.recipients]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate certificate_id values in the same request are not allowed")
        if len(self.recipients) > settings.max_recipients:
            raise ValueError(f"recipient list exceeds maximum of {settings.max_recipients}")
        return self


class GenerationJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    status: str
    total_count: int
    processed_count: int
    success_count: int
    failure_count: int
    created_at: dt.datetime


class JobStatusResponse(GenerationJobResponse):
    progress_percentage: float
    started_at: dt.datetime | None
    completed_at: dt.datetime | None


class JobCertificateItem(BaseModel):
    certificate_id: str
    recipient_name: str
    recipient_email: str
    status: str
    download_url: str | None = None
    error_message: str | None = None


class JobCertificatesResponse(BaseModel):
    job_id: str
    items: list[JobCertificateItem]
