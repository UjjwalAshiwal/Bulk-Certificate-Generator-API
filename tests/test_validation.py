"""Input validation: every malformed shape must yield 422 (or 400 for dupes in DB)."""

from tests.conftest import _payload, make_recipient


def test_empty_recipients_rejected(client):
    r = client.post("/api/v1/generation-jobs", json=_payload([]))
    assert r.status_code == 422, r.text


def test_malformed_email_rejected(client):
    r = client.post(
        "/api/v1/generation-jobs", json=_payload([make_recipient(1, email="not-an-email")])
    )
    assert r.status_code == 422, r.text


def test_missing_name_rejected(client):
    rec = make_recipient(1)
    del rec["name"]
    r = client.post("/api/v1/generation-jobs", json=_payload([rec]))
    assert r.status_code == 422, r.text


def test_blank_name_rejected(client):
    r = client.post("/api/v1/generation-jobs", json=_payload([make_recipient(1, name="   ")]))
    assert r.status_code == 422, r.text


def test_missing_certificate_id_rejected(client):
    rec = make_recipient(1)
    del rec["certificate_id"]
    r = client.post("/api/v1/generation-jobs", json=_payload([rec]))
    assert r.status_code == 422, r.text


def test_oversized_recipient_list_rejected(client):
    recs = [make_recipient(i) for i in range(10001)]
    r = client.post("/api/v1/generation-jobs", json=_payload(recs))
    assert r.status_code == 422, r.text


def test_duplicate_certificate_ids_rejected(client):
    r = client.post(
        "/api/v1/generation-jobs",
        json=_payload([make_recipient(1), make_recipient(2, certificate_id="CERT-001")]),
    )
    assert r.status_code == 422, r.text


def test_missing_event_fields_rejected(client):
    body = _payload([make_recipient(1)])
    del body["event_name"]
    r = client.post("/api/v1/generation-jobs", json=body)
    assert r.status_code == 422, r.text
