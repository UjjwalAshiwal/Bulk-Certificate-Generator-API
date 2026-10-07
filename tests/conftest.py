"""Isolated test setup: in-memory SQLite, temp storage, no real PostgreSQL."""

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db import database
from app.db.database import Base, get_db
from app.main import app


def _payload(recipients, **overrides):
    body = {
        "event_name": "Python Bootcamp 2026",
        "event_date": "2026-10-07",
        "issuer_name": "Example Organization",
        "recipients": recipients,
    }
    body.update(overrides)
    return body


def make_recipient(i, **overrides):
    r = {
        "name": f"Person {i}",
        "email": f"person{i}@example.com",
        "certificate_id": f"CERT-{i:03d}",
    }
    r.update(overrides)
    return r


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "generated"))
    test_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(database, "SessionLocal", TestSession)
    monkeypatch.setattr(database, "engine", test_engine)

    def override_db():
        s = TestSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    test_engine.dispose()


def wait_until_terminal(client: TestClient, job_id: str, timeout: float = 30.0) -> dict:
    """Poll until the job reaches COMPLETED / COMPLETED_WITH_ERRORS / FAILED."""
    deadline = time.time() + timeout
    while True:
        r = client.get(f"/api/v1/generation-jobs/{job_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        if body["status"] in ("COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED"):
            return body
        assert time.time() < deadline, f"timed out waiting for job {job_id}: {body}"
        time.sleep(0.05)
