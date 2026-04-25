from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import async_session
from app.routers import auth, pipeline, projects, sse, tasks
from app.routers.auth import ensure_owner_exists

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_session() as db:
        await ensure_owner_exists(db)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(pipeline.router)
app.include_router(sse.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": settings.app_name}
