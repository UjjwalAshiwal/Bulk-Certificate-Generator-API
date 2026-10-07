# Bulk Certificate Generator

Backend API that accepts **one request with a list of recipients** and generates a PDF
certificate for each of them — asynchronously, with per-certificate failure isolation,
progress tracking, and download endpoints.

## Problem & solution

Hand-generating certificates (one request/file per recipient) does not scale. This service
accepts a single bulk request (`event + recipients`), persists a **job** with one
**certificate row per recipient**, processes every row in a background worker, and lets the
client poll progress, inspect per-recipient results, and download each PDF.

## Architecture

```
Client
  ↓  POST /api/v1/generation-jobs (202 Accepted)
FastAPI
  ↓  validate → create job + PENDING certificate rows (PostgreSQL)
Background worker (FastAPI BackgroundTasks → certificate_worker.process_job)
  ↓  per recipient: render PDF (ReportLab) → save (storage service)
Filesystem storage (generated/<job_id>/<certificate_id>.pdf)
  ↓
Client polls GET /api/v1/generation-jobs/{id}, lists results,
downloads GET /api/v1/certificates/{certificate_id}
```

## Technology choices

| Choice | Why |
|---|---|
| FastAPI | Async-ready API, Pydantic v2 validation → automatic 422s, free OpenAPI at `/docs` |
| PostgreSQL | Durable job + certificate state, constraints (`UNIQUE`, FK), concurrent-safe counters |
| SQLAlchemy 2.x | Typed `Mapped` models, session-per-job in the worker |
| ReportLab | Pure-Python PDF generation, no binary template or external service needed |
| FastAPI BackgroundTasks | Zero extra infrastructure (no Redis/Celery/Kafka) — right-sized for this assignment; the worker is a plain function, so it can move to Celery/RQ later unchanged |
| Alembic | Versioned migrations instead of `create_all()` |
| Pytest + HTTPX/TestClient | Tests exercise real HTTP routes, real PDFs, real DB rows |
| Uvicorn | ASGI server |

## Project structure

```
app/
  main.py                 FastAPI factory, /health, startup recovery, error handler
  api/routes/jobs.py      POST jobs, GET status, GET job certificates
  api/routes/certificates.py  GET certificate PDF download
  core/config.py          Pydantic Settings (DATABASE_URL, STORAGE_DIR, …)
  core/logging.py         Structured logs with job_id / certificate_id
  db/database.py          Engine + SessionLocal + get_db dependency
  db/models/              GenerationJob, Certificate
  schemas/                Request/response models (validation lives here)
  services/job_service.py     Job creation + reads (no PDF logic)
  services/certificate_service.py  ReportLab rendering (the template, in code)
  services/storage_service.py Filesystem abstraction (swap for S3 later)
  workers/certificate_worker.py   Background loop with failure isolation
  utils/ids.py            UUID generation
migrations/               Alembic env + versions (initial: 0001_initial)
templates/                Note on the predefined design (code-defined, no editor)
generated/                PDF output dir (gitignored except .gitkeep)
tests/                    conftest (isolated SQLite) + 6 test modules
```

## Setup

```bash
git clone <repo-url>
cd bulk-certificate-generator
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[test]"
cp .env.example .env               # optional; defaults work for local dev
```

Requires Python 3.12+ and Docker (for PostgreSQL).

## Database

```bash
docker compose up -d postgres      # start PostgreSQL on localhost:5432
alembic upgrade head               # create generation_jobs + certificates
```

Configuration (`DATABASE_URL`, `STORAGE_DIR`, `LOG_LEVEL`, `MAX_RECIPIENTS`) comes from
`.env` / environment via `app/core/config.py`. Never commit real secrets (see `.env.example`).

## Running

```bash
docker compose up -d postgres
alembic upgrade head
uvicorn app.main:app --reload
```

OpenAPI docs: http://localhost:8000/docs (also `/redoc`). Health: `GET /health`
returns `{"status": "ok", "database": "ok"}`.

## Tests

```bash
pytest
```

Tests use an **isolated in-memory SQLite database** and a temp storage dir — they never
touch your real PostgreSQL. What they cover:

- `test_jobs.py` — valid creation (202 + QUEUED), repeated status reads, health
- `test_validation.py` — empty list, bad email, missing/blank name, missing cert id,
  10,001-recipient oversize, duplicate ids, missing event fields
- `test_certificate_generation.py` — real PDF bytes (`%PDF`, non-empty), recipient-specific
  content verified by decoding page streams, distinct PDFs per recipient
- `test_job_progress.py` — 0/N, partial, N/N progress derivation + counter invariant
- `test_failure_handling.py` — fault-injected renderer fails 1 of 3; all 3 still processed,
  `3/3/2/1 COMPLETED_WITH_ERRORS`, failed row carries a structured error, others downloadable
- `test_certificate_retrieval.py` — PDF download, 404s, failed-cert 422, no path leaks

## API usage

Create a job (async → `202 Accepted`):

```bash
curl -X POST http://localhost:8000/api/v1/generation-jobs \
  -H "Content-Type: application/json" \
  -d '{
    "event_name": "Python Bootcamp 2026",
    "event_date": "2026-10-07",
    "issuer_name": "Example Organization",
    "recipients": [
      {"name": "Ujjwal Ashiwal", "email": "ujjwal@example.com", "certificate_id": "CERT-001"},
      {"name": "Rahul Sharma", "email": "rahul@example.com", "certificate_id": "CERT-002"}
    ]
  }'
# → {"job_id": "<uuid>", "status": "QUEUED", "total_count": 2, ...}
```

Check status (progress is derived, not stored):

```bash
curl http://localhost:8000/api/v1/generation-jobs/<JOB_ID>
# → {"status": "PROCESSING", "total_count": 100, "processed_count": 67,
#    "success_count": 64, "failure_count": 3, "progress_percentage": 67.0, ...}
```

List per-certificate results:

```bash
curl http://localhost:8000/api/v1/generation-jobs/<JOB_ID>/certificates
```

Download a certificate:

```bash
curl -o certificate.pdf http://localhost:8000/api/v1/certificates/CERT-001
```

### Validation rules

- `name`: 1–200 chars, blank rejected
- `email`: valid email (Pydantic `EmailStr`)
- `certificate_id`: 1–100 chars, unique per request; globally unique in the DB so the
  download URL is unambiguous (stricter than per-job — see Design decisions)
- `recipients`: 1–10,000 items (`MAX_RECIPIENTS` env-overridable)
- Malformed requests → `422`; duplicate ids → `422` at validation, `400` if the id is
  already used by another job; unknown job/certificate → `404`; failed certificate
  download → `422` with the recorded reason; unexpected errors → `500` without stack traces

## Design decisions

- **Asynchronous generation.** The API persists the job and returns `202` immediately;
  the worker runs after. A 10,000-recipient job must not hold an HTTP connection open.
- **Failure isolation.** Each certificate has its own try/except + commit. One bad row
  records `status=FAILED` + `error_message` and the loop continues. The per-certificate
  step never raises, so even a database error on one row cannot abort the rest.
  A job is only ever claimed from `QUEUED`, so a duplicate dispatch is a no-op rather
  than a double-count. Invariant:
  `success_count + failure_count == processed_count == total_count` at the end.
- **Job status meanings.** `COMPLETED` = all succeeded; `COMPLETED_WITH_ERRORS` = fully
  processed with ≥1 item failure; `FAILED` = the job itself crashed (never for single bad
  recipients).
- **Transactions.** No mega-transaction: one commit per certificate (row + counters
  together, so they stay consistent). If PDF rendering succeeds but the DB commit fails,
  the file may exist without a SUCCESS row — documented, acceptable here; production would
  write via a transaction-aware outbox or object store with server-side naming.
- **Database model.** UUID string PKs (nothing sequential exposed); `certificates.job_id`
  FK with cascade; indexes on statuses/ids; `UNIQUE(job_id, certificate_identifier)` plus
  global `UNIQUE(certificate_identifier)` for unambiguous downloads.
- **Filesystem storage.** `StorageService` (`save/get/exists`) hides paths; files live at
  `generated/<job_id>/<certificate_id>.pdf` (sanitized, deterministic, collision-proof).
  Internal `file_path` is never serialized to clients.
- **Progress.** `progress_percentage = round(processed/total*100, 1)` computed on read.
- **Restart.** `BackgroundTasks` are in-process: a crash loses in-flight work. On startup,
  jobs stuck in `PROCESSING` are marked `FAILED` (visible instead of stuck forever);
  `QUEUED` jobs are left untouched. True durability needs a persistent queue (see below).
- **Duplicates.** Duplicate `certificate_id` in one request → rejected (`422`); reuse of an
  id from another job → `400` (global uniqueness keeps `GET /certificates/{id}` unambiguous).

## Limitations (honest)

- Local filesystem storage — not shared across instances, no CDN.
- Background work is lost on crash mid-job (mitigated only by the startup FAILED-marking).
- No auth, no rate limiting — outside assignment scope.
- Single worker loop; no parallelism within a job.
- `certificate_id` global uniqueness is stricter than the spec's per-job requirement.
- The built-in Helvetica font covers Latin-1 only: names/text outside Latin-1 fail
  loudly per-recipient (`FAILED` with a clear reason) instead of silently rendering
  a certificate with a missing name. Full Unicode needs an embedded TTF font.

## Production improvements (not implemented)

- Object storage (S3/GCS) behind the existing `storage_service` interface.
- Durable queue (Celery + Redis / RQ / DB-backed queue) with retries and multiple workers.
- Auth (API keys/OAuth2), rate limiting, idempotency keys for duplicate job submits.
- Observability: metrics (jobs in flight, failure rate), tracing, alerting.
- Horizontal scaling: chunked job partitions, parallel workers, read replicas.

## Makefile

```bash
make install   # pip install -e ".[test]"
make dev       # uvicorn --reload
make test      # pytest
make lint      # ruff check .
make format    # ruff format + fix
make migrate   # alembic upgrade head
make db-up     # docker compose up -d postgres
make db-down   # docker compose down
```

## Interview cheat-sheet

1. **Why FastAPI?** Validation + OpenAPI for free; async-ready; BackgroundTasks suffice here.
2. **Why PostgreSQL?** Durable state + constraints; counters survive restarts.
3. **Why async?** Bulk jobs take minutes; `202` + polling beats an open connection.
4. **Why not synchronous?** Timeouts, retries, and client UX all break at 10k recipients.
5. **Progress?** Derived `processed/total`; counters committed per certificate.
6. **One cert fails?** Caught, recorded, loop continues → `COMPLETED_WITH_ERRORS`.
7. **Storage?** `generated/<job>/<cert>.pdf` via a swappable service; paths never exposed.
8. **Crash mid-job?** In-flight work lost; startup marks `PROCESSING`→`FAILED`. Durable queue would fix it.
9. **100k certs?** Chunked partitions + N workers + object storage + DB queue.
10. **S3?** Implement `save/get/exists` against boto3; store the key in `file_path`.
11. **Auth?** API-key dependency or OAuth2 bearer on the routers.
12. **Durable processing?** Persistent queue + at-least-once delivery + idempotent per-cert writes.
13. **Duplicate jobs?** Idempotency-Key header hashed to a unique job constraint.
14. **Observability?** Structured logs already carry ids; add metrics/tracing next.
