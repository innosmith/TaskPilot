import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import async_session
from app.routers import (
    agent_jobs,
    auth,
    memory,
    pipeline,
    projects,
    search,
    sse,
    tags,
    tasks,
    unsplash,
)
from app.routers import settings as user_settings
from app.routers.auth import ensure_owner_exists
from app.services.nanobot_bridge import start_bridge, stop_bridge

logging.basicConfig(level=logging.INFO)
app_settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_session() as db:
        await ensure_owner_exists(db)
    await start_bridge()
    yield
    await stop_bridge()


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
app.include_router(sse.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": app_settings.app_name}
