"""Filesystem storage abstraction (swap for S3/GCS in production)."""

import re
from pathlib import Path

from app.core.config import settings

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _base_dir() -> Path:
    return Path(settings.storage_dir)


def safe_filename(value: str) -> str:
    return _SAFE.sub("_", value).strip("._") or "cert"


def save_certificate(job_id: str, certificate_id: str, pdf_bytes: bytes) -> str:
    """Persist PDF bytes. Returns the stored path (never exposed via API)."""
    directory = _base_dir() / safe_filename(job_id)
    directory.mkdir(parents=True, exist_ok=True)
    # Job-scoped directory + sanitized id. Counter suffix guarantees no
    # recipient ever overwrites another's file, however adversarial the ids.
    base = safe_filename(certificate_id)
    path = directory / f"{base}.pdf"
    counter = 1
    while path.exists():
        counter += 1
        path = directory / f"{base}_{counter}.pdf"
    path.write_bytes(pdf_bytes)
    return str(path)


def get_certificate_path(stored_path: str) -> Path | None:
    p = Path(stored_path)
    return p if p.is_file() else None
