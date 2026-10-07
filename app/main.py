"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.routes import certificates, jobs
from app.core.config import settings
from app.core.logging import logger
from app.db import database
from app.services.job_service import now_utc


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.storage_dir).mkdir(parents=True, exist_ok=True)
    _recover_interrupted_jobs()
    yield


def _recover_interrupted_jobs() -> None:
    """Mark jobs stuck in PROCESSING as FAILED after a restart.

    BackgroundTasks live in-process, so a crash loses in-flight work. Failing
    them visibly (instead of leaving PROCESSING forever) is the honest minimal
    behavior; QUEUED jobs are left for the next deploy to pick up.
    """
    from app.db.models.generation_job import JOB_FAILED, JOB_PROCESSING

    db = database.SessionLocal()
    try:
        from app.db.models.generation_job import GenerationJob

        stuck = db.query(GenerationJob).filter(GenerationJob.status == JOB_PROCESSING).all()
        for job in stuck:
            job.status = JOB_FAILED
            job.completed_at = now_utc()
        db.commit()
        if stuck:
            logger.warning("marked %d interrupted job(s) as FAILED", len(stuck))
    except Exception as exc:
        logger.warning("startup recovery skipped: %s", exc)
        db.rollback()
    finally:
        db.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Bulk Certificate Generator",
        description="Accept a bulk recipient list, generate PDF certificates asynchronously, "
        "track progress, and serve downloads.",
        version="1.0.0",
        lifespan=lifespan,
    )

    @app.exception_handler(Exception)
    async def unhandled(request, exc):  # noqa: ANN001, ANN202
        logger.exception("unhandled error path=%s error=%s", request.url.path, exc)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    @app.get("/health", summary="Health check", tags=["health"])
    def health():
        try:
            with database.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_status = "ok"
        except Exception as exc:
            logger.warning("health db check failed: %s", exc)
            db_status = "unavailable"
        return {"status": "ok", "database": db_status}

    app.include_router(jobs.router, prefix="/api/v1")
    app.include_router(certificates.router, prefix="/api/v1")
    return app


app = create_app()
