"""Adversarial edge cases: hostile inputs, stale state, idempotency, unicode."""

from pathlib import Path

from app.core.config import settings
from app.db import database
from app.db.models.certificate import Certificate
from app.workers.certificate_worker import process_job
from tests.conftest import _payload, make_recipient, wait_until_terminal


def test_whitespace_only_event_and_issuer_rejected(client):
    body = _payload([make_recipient(1)], event_name="   ")
    assert client.post("/api/v1/generation-jobs", json=body).status_code == 422
    body = _payload([make_recipient(1)], issuer_name="  ")
    assert client.post("/api/v1/generation-jobs", json=body).status_code == 422


def test_overlong_email_rejected_before_db(client):
    long_local = "a" * 300
    r = client.post(
        "/api/v1/generation-jobs",
        json=_payload([make_recipient(1, email=f"{long_local}@example.com")]),
    )
    assert r.status_code == 422, r.text


def test_name_length_boundary(client):
    ok = _payload([make_recipient(1, name="A" * 200)])
    assert client.post("/api/v1/generation-jobs", json=ok).status_code == 202
    bad = _payload([make_recipient(2, name="B" * 201)])
    assert client.post("/api/v1/generation-jobs", json=bad).status_code == 422


def test_malformed_and_unexpected_payloads(client):
    base = _payload([make_recipient(1)])
    for broken in [
        {**base, "event_date": "not-a-date"},
        {**base, "event_date": "2026-13-45"},
        {**base, "recipients": None},
        {**base, "recipients": {"name": "x"}},
        [make_recipient(1)],
        "just a string",
    ]:
        r = client.post("/api/v1/generation-jobs", json=broken)
        assert r.status_code == 422, (broken, r.text)


def test_cross_job_duplicate_certificate_id_rejected(client):
    first = _payload([make_recipient(1, certificate_id="SHARED-001")])
    assert client.post("/api/v1/generation-jobs", json=first).status_code == 202
    second = _payload([make_recipient(2, certificate_id="SHARED-001")])
    r = client.post("/api/v1/generation-jobs", json=second)
    assert r.status_code == 400
    assert "already in use" in r.json()["detail"]


def test_pending_certificate_download_is_422_not_500(client):
    # Bypass the background worker: row exists but was never processed.
    from app.schemas.jobs import GenerationJobCreate
    from app.services import job_service

    db = database.SessionLocal()
    try:
        job = job_service.create_job(
            db, GenerationJobCreate(**_payload([make_recipient(1, certificate_id="PEND-001")]))
        )
        assert job.status == "QUEUED"  # persisted but never processed: no background task
    finally:
        db.close()
    r = client.get("/api/v1/certificates/PEND-001")
    assert r.status_code == 422
    assert "not ready" in r.json()["detail"]


def test_stale_success_record_with_missing_file_returns_404(client):
    r = client.post("/api/v1/generation-jobs", json=_payload([make_recipient(1)]))
    job_id = r.json()["job_id"]
    wait_until_terminal(client, job_id)

    db = database.SessionLocal()
    try:
        cert = db.query(Certificate).filter_by(certificate_identifier="CERT-001").one()
        stored = Path(cert.file_path)
        assert stored.is_file()
        stored.unlink()  # simulate lost file / unshared volume
    finally:
        db.close()

    r = client.get("/api/v1/certificates/CERT-001")
    assert r.status_code == 404


def test_rerun_on_terminal_job_is_noop(client):
    r = client.post(
        "/api/v1/generation-jobs", json=_payload([make_recipient(1), make_recipient(2)])
    )
    job_id = r.json()["job_id"]
    before = wait_until_terminal(client, job_id)
    process_job(job_id)  # duplicate dispatch must not double-count
    process_job(job_id)
    after = client.get(f"/api/v1/generation-jobs/{job_id}").json()
    assert after == before
    assert after["processed_count"] == 2
    assert after["success_count"] + after["failure_count"] == after["processed_count"]


def test_unicode_latin_name_succeeds(client):
    r = client.post(
        "/api/v1/generation-jobs",
        json=_payload([make_recipient(1, name="José María Müller")]),
    )
    assert r.status_code == 202
    final = wait_until_terminal(client, r.json()["job_id"])
    assert final["status"] == "COMPLETED"
    dl = client.get("/api/v1/certificates/CERT-001")
    assert dl.status_code == 200
    assert dl.content.startswith(b"%PDF")


def test_non_latin_name_fails_loudly_not_silently(client):
    recs = [
        make_recipient(1, name="山田太郎", certificate_id="CJK-001"),
        make_recipient(2, name="Plain Jane", certificate_id="LAT-002"),
    ]
    job_id = client.post("/api/v1/generation-jobs", json=_payload(recs)).json()["job_id"]
    final = wait_until_terminal(client, job_id)
    assert final["status"] == "COMPLETED_WITH_ERRORS"
    assert final["success_count"] == 1 and final["failure_count"] == 1
    items = {
        i["certificate_id"]: i
        for i in client.get(f"/api/v1/generation-jobs/{job_id}/certificates").json()["items"]
    }
    assert items["CJK-001"]["status"] == "FAILED"
    assert "cannot render" in items["CJK-001"]["error_message"]
    assert items["LAT-002"]["status"] == "SUCCESS"


def test_path_traversal_certificate_id_cannot_escape_storage(client):
    evil = "../../evil-escape"
    body = _payload([make_recipient(1, name="Evil Tester", certificate_id=evil)])
    r = client.post("/api/v1/generation-jobs", json=body)
    # Either rejected or safely contained — never a file outside storage_dir.
    if r.status_code == 202:
        final = wait_until_terminal(client, r.json()["job_id"])
        assert final["status"] == "COMPLETED"
        base = Path(settings.storage_dir).resolve()
        db = database.SessionLocal()
        try:
            cert = db.query(Certificate).filter_by(certificate_identifier=evil).one()
            resolved = Path(cert.file_path).resolve()
        finally:
            db.close()
        assert str(resolved).startswith(str(base)), resolved
    else:
        assert r.status_code == 422


def test_success_file_exists_on_disk_and_repeated_downloads_match(client):
    r = client.post(
        "/api/v1/generation-jobs", json=_payload([make_recipient(1), make_recipient(2)])
    )
    job_id = r.json()["job_id"]
    wait_until_terminal(client, job_id)

    db = database.SessionLocal()
    try:
        paths = [
            c.file_path for c in db.query(Certificate).filter(Certificate.job_id == job_id).all()
        ]
    finally:
        db.close()
    assert len(paths) == 2 and len(set(paths)) == 2  # distinct files, no collision
    for p in paths:
        assert Path(p).is_file() and Path(p).stat().st_size > 1000

    first = client.get("/api/v1/certificates/CERT-001")
    second = client.get("/api/v1/certificates/CERT-001")
    assert first.status_code == second.status_code == 200
    assert first.content == second.content
