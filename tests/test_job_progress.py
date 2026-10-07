"""Job progress: 0/N at creation, N/N at completion, derived percentage."""

from app.db.models.generation_job import GenerationJob
from app.services.job_service import progress_percentage
from tests.conftest import _payload, make_recipient, wait_until_terminal


def _job(total, processed, success, failure):
    return GenerationJob(
        id="x",
        event_name="e",
        event_date="2026-10-07",  # type: ignore[arg-type]
        issuer_name="i",
        status="PROCESSING",
        total_count=total,
        processed_count=processed,
        success_count=success,
        failure_count=failure,
    )


def _assert_counts_consistent(job):
    assert job.success_count + job.failure_count == job.processed_count


def test_progress_zero_of_n():
    job = _job(100, 0, 0, 0)
    assert progress_percentage(job) == 0.0
    _assert_counts_consistent(job)


def test_progress_partial():
    job = _job(100, 67, 64, 3)
    assert progress_percentage(job) == 67.0
    _assert_counts_consistent(job)


def test_progress_full():
    job = _job(5, 5, 5, 0)
    assert progress_percentage(job) == 100.0
    _assert_counts_consistent(job)


def test_end_to_end_counters_and_invariant(client):
    recs = [make_recipient(i) for i in range(1, 6)]
    created = client.post("/api/v1/generation-jobs", json=_payload(recs)).json()
    assert created["processed_count"] == 0  # 0/N at creation

    final = wait_until_terminal(client, created["job_id"])
    assert final["total_count"] == 5
    assert final["processed_count"] == 5  # N/N at completion
    assert final["success_count"] + final["failure_count"] == final["processed_count"]
    assert final["progress_percentage"] == 100.0
