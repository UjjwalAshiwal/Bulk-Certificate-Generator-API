"""Failure isolation: one bad certificate must not stop the rest of the job."""

from app.services import certificate_service
from tests.conftest import _payload, make_recipient, wait_until_terminal


def test_individual_failure_does_not_stop_job(client, monkeypatch):
    real_render = certificate_service.render_certificate_pdf

    def flaky(*, recipient_name, **kwargs):
        if kwargs.get("certificate_id") == "CERT-002":
            raise RuntimeError("simulated renderer crash")
        return real_render(recipient_name=recipient_name, **kwargs)

    monkeypatch.setattr(certificate_service, "render_certificate_pdf", flaky)

    recs = [make_recipient(1), make_recipient(2), make_recipient(3)]
    r = client.post("/api/v1/generation-jobs", json=_payload(recs))
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]

    final = wait_until_terminal(client, job_id)
    assert final["total_count"] == 3
    assert final["processed_count"] == 3
    assert final["success_count"] == 2
    assert final["failure_count"] == 1
    assert final["status"] == "COMPLETED_WITH_ERRORS"

    items = client.get(f"/api/v1/generation-jobs/{job_id}/certificates").json()["items"]
    by_id = {i["certificate_id"]: i for i in items}
    assert by_id["CERT-001"]["status"] == "SUCCESS"
    assert by_id["CERT-002"]["status"] == "FAILED"
    assert by_id["CERT-002"]["error_message"]  # structured, not a stack trace leak
    assert "simulated renderer crash" in by_id["CERT-002"]["error_message"]
    assert by_id["CERT-003"]["status"] == "SUCCESS"
    assert by_id["CERT-001"]["download_url"]
    assert by_id["CERT-002"]["download_url"] is None
