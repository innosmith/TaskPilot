"""Router für Code-Execution via Chat-Interface (Schicht 2).

Generiert Python-Code via LLM und führt ihn in der Docker-Sandbox aus.
Unterstützt zwei Flows:
1. generate_and_execute: LLM generiert Code aus natürlicher Sprache → Preview → Execute
2. execute_direct: Berater gibt Code direkt ein → Execute
"""

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path

import litellm
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from app.auth.deps import get_current_user, get_current_user_light
from app.config import get_settings
from app.database import get_db, async_session
from app.models import User
from app.models.models import LlmConversation, LlmMessage

litellm.drop_params = True

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/code", tags=["code-execute"])

SANDBOX_SCRIPT = Path(__file__).parent.parent.parent.parent / "mcp-sandbox" / "server.py"

CODE_GENERATION_SYSTEM_PROMPT = """Du bist ein Python-Code-Generator für Datenanalyse und Automation.
Deine Aufgabe ist es, sauberen, ausführbaren Python-Code zu generieren.

REGELN:
- Antworte NUR mit dem Python-Code (kein Markdown, keine Erklärungen drumherum)
- Der Code muss eigenständig lauffähig sein
- Input-Dateien liegen in /input/ (read-only)
- Output-Dateien in /workspace/ schreiben
- Ergebnisse via print() ausgeben (wird als Output erfasst)
- Verfügbare Packages: pandas, numpy, matplotlib, seaborn, openpyxl, scipy, pyyaml, jinja2, tabulate, xlsxwriter
- KEIN subprocess, os.system, exec(), eval(), requests, urllib
- KEIN Netzwerkzugriff (kein API-Call, kein Download)
- Robustes Error-Handling mit try/except
- Schweizer Deutsch in Kommentaren (ss statt ß)"""


async def _generate_code(
    task_description: str,
    model: str,
    input_file_names: list[str] | None = None,
) -> str:
    """LLM aufrufen um Python-Code zu generieren (nicht-streamend, für /generate)."""
    settings = get_settings()

    if settings.openai_api_key:
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key
    if settings.anthropic_api_key:
        os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

    user_prompt = f"Aufgabe: {task_description}"
    if input_file_names:
        user_prompt += f"\n\nVerfügbare Input-Dateien in /input/: {', '.join(input_file_names)}"

    response = await litellm.acompletion(
        model=model,
        messages=[
            {"role": "system", "content": CODE_GENERATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        api_base="http://localhost:11434" if model.startswith("ollama/") else None,
    )

    code = response.choices[0].message.content.strip()
    return _extract_code(code)


def _extract_code(raw: str) -> str:
    """Extrahiert reinen Python-Code aus LLM-Antwort (entfernt Markdown-Fences)."""
    code = raw.strip()
    if code.startswith("```python"):
        code = code[len("```python"):].strip()
    if code.startswith("```"):
        code = code[3:].strip()
    if code.endswith("```"):
        code = code[:-3].strip()
    return code


async def _generate_code_streaming(
    task_description: str,
    model: str,
    input_file_names: list[str] | None = None,
):
    """LLM-Streaming-Generator: yielded (event_type, content) Tupel.

    event_type: 'thinking' | 'token' | 'done'
    """
    settings = get_settings()

    if settings.openai_api_key:
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key
    if settings.anthropic_api_key:
        os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

    user_prompt = f"Aufgabe: {task_description}"
    if input_file_names:
        user_prompt += f"\n\nVerfügbare Input-Dateien in /input/: {', '.join(input_file_names)}"

    response = await asyncio.wait_for(
        litellm.acompletion(
            model=model,
            messages=[
                {"role": "system", "content": CODE_GENERATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            stream=True,
            api_base="http://localhost:11434" if model.startswith("ollama/") else None,
        ),
        timeout=120,
    )

    full_content = ""
    thinking_buffer = ""
    in_thinking = False

    async for chunk in response:
        delta = chunk.choices[0].delta if chunk.choices else None
        if not delta:
            continue

        # Reasoning/Thinking content (separate Felder bei manchen Providern)
        reasoning = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
        if reasoning:
            thinking_buffer += reasoning
            yield ("thinking", reasoning)
            continue

        text = delta.content or ""
        if not text:
            continue

        # Erkennung von <think>...</think> Blöcken (Ollama/Qwen)
        if "<think>" in text and not in_thinking:
            parts = text.split("<think>", 1)
            if parts[0]:
                full_content += parts[0]
                yield ("token", parts[0])
            in_thinking = True
            text = parts[1]

        if in_thinking:
            if "</think>" in text:
                parts = text.split("</think>", 1)
                thinking_buffer += parts[0]
                yield ("thinking", parts[0])
                in_thinking = False
                remainder = parts[1]
                if remainder:
                    full_content += remainder
                    yield ("token", remainder)
            else:
                thinking_buffer += text
                yield ("thinking", text)
        else:
            full_content += text
            yield ("token", text)

    yield ("done", full_content)


async def _execute_in_sandbox(code: str, input_files: dict | None = None, timeout: int = 300) -> dict:
    """Code in Docker-Sandbox ausführen (importiert Logik aus mcp-sandbox)."""
    try:
        result = await asyncio.create_subprocess_exec(
            "docker", "image", "inspect", "taskpilot-sandbox:latest",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await result.wait()
        if result.returncode != 0:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Docker-Image 'taskpilot-sandbox:latest' nicht gefunden. Bitte bauen: docker build -t taskpilot-sandbox:latest -f docker/sandbox/Dockerfile docker/sandbox/",
                "run_id": None,
            }
    except Exception:
        return {
            "success": False, "stdout": "", "stderr": "Docker nicht verfügbar", "run_id": None,
        }

    sys.path.insert(0, str(SANDBOX_SCRIPT.parent))
    from server import _execute_in_sandbox as sandbox_exec
    sys.path.pop(0)

    return await sandbox_exec(code, input_files, timeout)


@router.post("/conversations/{conversation_id}/generate")
async def generate_code(
    conversation_id: uuid.UUID,
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Code aus natürlicher Sprache generieren (ohne Ausführung).

    Gibt den generierten Code zurück. Berater kann ihn reviewen und dann
    via /execute bestätigen.
    """
    result = await db.execute(
        select(LlmConversation).where(LlmConversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Konversation nicht gefunden")

    from app.services.llm_defaults import get_default_local_model_from_settings

    task_description = body.get("content", "")
    user_settings = user.settings or {}
    code_model_fallback = user_settings.get("llm_default_local_model") or "ollama/qwen2.5-coder:32b"
    model = body.get("model") or code_model_fallback
    input_file_names = body.get("input_file_names", [])

    if not task_description:
        raise HTTPException(status_code=400, detail="content (Aufgabenbeschreibung) fehlt")

    user_msg = LlmMessage(
        conversation_id=conv.id,
        role="user",
        content=task_description,
    )
    db.add(user_msg)
    await db.flush()

    try:
        code = await _generate_code(task_description, model, input_file_names)
    except Exception as e:
        logger.exception("Code-Generierung fehlgeschlagen")
        raise HTTPException(status_code=500, detail=f"Code-Generierung fehlgeschlagen: {str(e)}")

    assistant_msg = LlmMessage(
        conversation_id=conv.id,
        role="assistant",
        content=f"```python\n{code}\n```",
        model=model,
    )
    db.add(assistant_msg)
    await db.commit()

    return {
        "code": code,
        "model": model,
        "message_id": str(assistant_msg.id),
        "conversation_id": str(conv.id),
        "status": "generated",
    }


@router.post("/conversations/{conversation_id}/execute")
async def execute_code(
    conversation_id: uuid.UUID,
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generierten oder manuellen Code in der Sandbox ausführen.

    Gibt das Ergebnis (stdout, stderr, Dateien) zurück.
    Dies ist das HITL-Gate: Der Berater hat den Code gesehen und bestätigt die Ausführung.
    """
    result = await db.execute(
        select(LlmConversation).where(LlmConversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Konversation nicht gefunden")

    code = body.get("code", "")
    input_files = body.get("input_files")
    timeout = min(body.get("timeout_seconds", 300), 900)

    if not code.strip():
        raise HTTPException(status_code=400, detail="Kein Code übergeben")

    logger.info("[code-execute] Sandbox-Ausführung gestartet (conv=%s, timeout=%ds)", conversation_id, timeout)

    exec_result = await _execute_in_sandbox(code, input_files, timeout)

    output_parts = []
    if exec_result["success"]:
        output_parts.append("**Ausführung erfolgreich**")
        if exec_result.get("stdout"):
            output_parts.append(f"```\n{exec_result['stdout']}\n```")
        if exec_result.get("generated_files"):
            files_list = ", ".join(f["name"] for f in exec_result["generated_files"])
            output_parts.append(f"Erzeugte Dateien: {files_list}")
    else:
        output_parts.append("**Ausführung fehlgeschlagen**")
        if exec_result.get("error"):
            output_parts.append(f"Fehler: {exec_result['error']}")
        if exec_result.get("stderr"):
            output_parts.append(f"```\n{exec_result['stderr']}\n```")

    result_content = "\n\n".join(output_parts)

    result_msg = LlmMessage(
        conversation_id=conv.id,
        role="assistant",
        content=result_content,
    )
    db.add(result_msg)
    await db.commit()

    return {
        "success": exec_result["success"],
        "stdout": exec_result.get("stdout", ""),
        "stderr": exec_result.get("stderr", ""),
        "generated_files": exec_result.get("generated_files", []),
        "duration_seconds": exec_result.get("duration_seconds", 0),
        "run_id": exec_result.get("run_id"),
        "message_id": str(result_msg.id),
    }


@router.post("/conversations/{conversation_id}/generate-and-execute")
async def generate_and_execute(
    conversation_id: uuid.UUID,
    body: dict,
    user: User = Depends(get_current_user_light),
):
    """Code generieren UND ausführen in einem Schritt (für Chat-Flow mit impliziter Genehmigung).

    SSE-Stream: code_generated → executing → result
    """
    async with async_session() as db:
        result = await db.execute(
            select(LlmConversation).where(LlmConversation.id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="Konversation nicht gefunden")

        conv_id_str = str(conv.id)

    task_description = body.get("content", "")
    user_settings = user.settings or {}
    code_model_fallback = user_settings.get("llm_default_local_model") or "ollama/qwen2.5-coder:32b"
    model = body.get("model") or code_model_fallback
    input_files = body.get("input_files")
    timeout = min(body.get("timeout_seconds", 300), 900)

    if not task_description:
        raise HTTPException(status_code=400, detail="content (Aufgabenbeschreibung) fehlt")

    async def generate():
        t_start = time.time()

        yield {"event": "status", "data": json.dumps({"phase": "connecting", "model": model})}

        async with async_session() as save_db:
            user_msg = LlmMessage(
                conversation_id=uuid.UUID(conv_id_str),
                role="user",
                content=task_description,
            )
            save_db.add(user_msg)
            await save_db.commit()

        yield {"event": "status", "data": json.dumps({"phase": "generating", "model": model})}

        try:
            input_file_names = list(input_files.keys()) if input_files else []
            full_code = ""
            async for event_type, content in _generate_code_streaming(
                task_description, model, input_file_names
            ):
                if event_type == "thinking":
                    yield {"event": "thinking", "data": json.dumps({"content": content})}
                elif event_type == "token":
                    yield {"event": "token", "data": json.dumps({"content": content})}
                elif event_type == "done":
                    full_code = content

            code = _extract_code(full_code)
        except asyncio.TimeoutError:
            yield {"event": "error", "data": json.dumps({"error": "Timeout: LLM hat nicht innerhalb von 120s geantwortet. Ist Ollama aktiv?"})}
            return
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": f"Code-Generierung fehlgeschlagen: {str(e)}"})}
            return

        yield {"event": "code_generated", "data": json.dumps({"code": code, "model": model})}
        yield {"event": "status", "data": json.dumps({"phase": "executing"})}

        exec_task = asyncio.create_task(_execute_in_sandbox(code, input_files, timeout))
        try:
            while True:
                done, _ = await asyncio.wait(
                    {exec_task},
                    timeout=20.0,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if exec_task in done:
                    exec_result = exec_task.result()
                    break
                # SSE-Keepalive: ohne Bytes schliessen manche Proxies (nginx ~60s, Tunnel ~100s).
                yield {"event": "keepalive", "data": "{}"}
        except Exception as e:
            if not exec_task.done():
                exec_task.cancel()
            yield {"event": "error", "data": json.dumps({"error": f"Sandbox fehlgeschlagen: {str(e)}"})}
            return

        async with async_session() as save_db:
            code_msg = LlmMessage(
                conversation_id=uuid.UUID(conv_id_str),
                role="assistant",
                content=f"```python\n{code}\n```",
                model=model,
            )
            save_db.add(code_msg)

            output_parts = []
            if exec_result["success"]:
                output_parts.append("**Ausführung erfolgreich**")
                if exec_result.get("stdout"):
                    output_parts.append(f"```\n{exec_result['stdout']}\n```")
            else:
                output_parts.append("**Ausführung fehlgeschlagen**")
                if exec_result.get("stderr"):
                    output_parts.append(f"```\n{exec_result['stderr']}\n```")

            result_msg = LlmMessage(
                conversation_id=uuid.UUID(conv_id_str),
                role="assistant",
                content="\n\n".join(output_parts),
            )
            save_db.add(result_msg)
            await save_db.commit()

        yield {"event": "result", "data": json.dumps({
            "success": exec_result["success"],
            "stdout": exec_result.get("stdout", ""),
            "stderr": exec_result.get("stderr", ""),
            "generated_files": exec_result.get("generated_files", []),
            "duration_seconds": exec_result.get("duration_seconds", 0),
        })}

        yield {"event": "done", "data": json.dumps({
            "elapsed_s": round(time.time() - t_start, 1),
        })}

    return EventSourceResponse(generate())
