"""Job creation: happy path + repeated status reads + health."""

from tests.conftest import _payload, make_recipient, wait_until_terminal


def test_create_valid_job_returns_202_queued(client):
    r = client.post(
        "/api/v1/generation-jobs", json=_payload([make_recipient(1), make_recipient(2)])
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "QUEUED"  # response snapshot taken before background runs
    assert body["total_count"] == 2
    assert body["processed_count"] == 0
    assert body["job_id"]

    # Background worker brings it to a terminal state.
    final = wait_until_terminal(client, body["job_id"])
    assert final["status"] == "COMPLETED"
    assert final["processed_count"] == 2
    assert final["success_count"] == 2
    assert final["failure_count"] == 0


def test_repeated_status_requests_are_stable(client):
    r = client.post("/api/v1/generation-jobs", json=_payload([make_recipient(1)]))
    job_id = r.json()["job_id"]
    first = wait_until_terminal(client, job_id)
    for _ in range(3):
        again = client.get(f"/api/v1/generation-jobs/{job_id}").json()
        assert again == first


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
