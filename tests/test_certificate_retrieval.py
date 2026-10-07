"""Retrieval: PDF download, failed-cert message, and 404s."""

from app.services import certificate_service
from tests.conftest import _payload, make_recipient, wait_until_terminal


def test_successful_certificate_returns_pdf(client):
    r = client.post("/api/v1/generation-jobs", json=_payload([make_recipient(1)]))
    job_id = r.json()["job_id"]
    wait_until_terminal(client, job_id)

    dl = client.get("/api/v1/certificates/CERT-001")
    assert dl.status_code == 200, dl.text
    assert dl.headers["content-type"] == "application/pdf"
    assert dl.content.startswith(b"%PDF")
    assert len(dl.content) > 1000


def test_nonexistent_certificate_returns_404(client):
    r = client.get("/api/v1/certificates/CERT-NOPE")
    assert r.status_code == 404
    assert r.json()["detail"] == "Certificate not found"


def test_failed_certificate_returns_meaningful_response(client, monkeypatch):
    def always_fail(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(certificate_service, "render_certificate_pdf", always_fail)
    r = client.post("/api/v1/generation-jobs", json=_payload([make_recipient(9)]))
    job_id = r.json()["job_id"]
    final = wait_until_terminal(client, job_id)
    assert final["status"] == "COMPLETED_WITH_ERRORS"

    dl = client.get("/api/v1/certificates/CERT-009")
    assert dl.status_code == 422
    assert "boom" in dl.json()["detail"]


def test_nonexistent_job_returns_404(client):
    r = client.get("/api/v1/generation-jobs/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
    r2 = client.get("/api/v1/generation-jobs/00000000-0000-0000-0000-000000000000/certificates")
    assert r2.status_code == 404


def test_job_results_list_success_and_download_urls(client):
    recs = [make_recipient(1), make_recipient(2)]
    job_id = client.post("/api/v1/generation-jobs", json=_payload(recs)).json()["job_id"]
    wait_until_terminal(client, job_id)

    body = client.get(f"/api/v1/generation-jobs/{job_id}/certificates").json()
    assert body["job_id"] == job_id
    assert len(body["items"]) == 2
    for item in body["items"]:
        assert item["status"] == "SUCCESS"
        assert item["download_url"].endswith(item["certificate_id"])
        assert "file_path" not in item  # no internal paths leaked
