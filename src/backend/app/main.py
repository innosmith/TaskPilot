import logging
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import get_settings
from app.database import async_session
from app.routers import (
    agent_jobs,
    auth,
    bexio,
    calendar,
    emails,
    intelligence,
    memory,
    models,
    pipedrive,
    pipeline,
    projects,
    search,
    sse,
    tags,
    tasks,
    toggl,
    triage,
    unsplash,
    uploads,
)
from app.routers import settings as user_settings
from app.routers.auth import ensure_owner_exists
from app.services.nanobot_worker import start_nanobot_worker, stop_nanobot_worker
from app.services.recurring import start_recurring_scheduler, stop_recurring_scheduler
from app.services.triage import start_triage_service, stop_triage_service

logging.basicConfig(level=logging.INFO)
app_settings = get_settings()

UPLOADS_DIR = pathlib.Path(__file__).resolve().parent.parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)
(UPLOADS_DIR / "avatars").mkdir(exist_ok=True)
(UPLOADS_DIR / "icons").mkdir(exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_session() as db:
        await ensure_owner_exists(db)

    # Verwaiste "running"-Jobs nach Server-Neustart bereinigen
    async with async_session() as db:
        result = await db.execute(
            text(
                "UPDATE agent_jobs "
                "SET status = 'failed', "
                "    error_message = 'Durch Server-Neustart abgebrochen', "
                "    completed_at = NOW() "
                "WHERE status = 'running' "
                "RETURNING id"
            )
        )
        stale_ids = result.scalars().all()
        if stale_ids:
            logging.getLogger("taskpilot.lifespan").warning(
                "Startup-Cleanup: %d verwaiste running-Jobs auf failed gesetzt: %s",
                len(stale_ids),
                [str(i) for i in stale_ids],
            )
        await db.commit()

    await start_nanobot_worker()
    await start_recurring_scheduler()
    await start_triage_service()
    yield
    await stop_triage_service()
    await stop_recurring_scheduler()
    await stop_nanobot_worker()


app = FastAPI(
    title=app_settings.app_name,
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(pipeline.router)
app.include_router(agent_jobs.router)
app.include_router(tags.router)
app.include_router(search.router)
app.include_router(memory.router)
app.include_router(user_settings.router)
app.include_router(unsplash.router)
app.include_router(uploads.router)
app.include_router(sse.router)
app.include_router(emails.router)
app.include_router(calendar.router)
app.include_router(triage.router)
app.include_router(models.router)
app.include_router(pipedrive.router)
app.include_router(toggl.router)
app.include_router(bexio.router)
app.include_router(intelligence.router)

app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


@app.get("/api/health")
async def health():
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok", "app": app_settings.app_name}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "db": "unreachable", "app": app_settings.app_name},
        )
