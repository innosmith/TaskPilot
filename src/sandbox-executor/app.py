"""HTTP-API des Sandbox-Executors.

Minimaler FastAPI-Service mit genau einem fachlichen Endpoint (``POST /execute``)
und einem Health-Check. Zugriff nur mit gültigem Bearer-Token
(``TP_SANDBOX_EXECUTOR_TOKEN``). Der Service wird in Prod/Int **nicht** auf einen
Host-Port veröffentlicht, sondern ist nur im internen Docker-Netz erreichbar.
"""

import hmac
import logging
import os

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from executor import (
    MAX_CODE_LENGTH,
    MAX_TIMEOUT_SECONDS,
    SANDBOX_IMAGE,
    execute_in_sandbox,
)

logger = logging.getLogger("sandbox_executor.api")

TOKEN = os.environ.get("TP_SANDBOX_EXECUTOR_TOKEN", "").strip()

app = FastAPI(title="TaskPilot Sandbox-Executor", version="1.0.0")


class ExecuteRequest(BaseModel):
    code: str
    input_files: dict[str, str] | None = None
    timeout_seconds: int = 300


def _check_auth(authorization: str | None) -> None:
    """Prüft den Bearer-Token in konstanter Zeit."""
    if not TOKEN:
        raise HTTPException(
            status_code=500,
            detail="Executor nicht konfiguriert: TP_SANDBOX_EXECUTOR_TOKEN fehlt",
        )
    expected = f"Bearer {TOKEN}"
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Ungültiges oder fehlendes Token")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "image": SANDBOX_IMAGE, "token_configured": bool(TOKEN)}


@app.post("/execute")
async def execute(req: ExecuteRequest, authorization: str | None = Header(default=None)) -> dict:
    _check_auth(authorization)

    code = (req.code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="Kein Code übergeben")
    if len(code) > MAX_CODE_LENGTH:
        raise HTTPException(
            status_code=413,
            detail=f"Code zu lang ({len(code)} Zeichen, max {MAX_CODE_LENGTH})",
        )

    timeout = max(1, min(req.timeout_seconds or 300, MAX_TIMEOUT_SECONDS))
    logger.info("execute: code_length=%d, timeout=%ds", len(code), timeout)

    return await execute_in_sandbox(code, req.input_files, timeout)
