"""Docker-Run-Logik für die Code-Sandbox (Schicht 2).

Dieser Prozess läuft in einem eigenen, minimalen Container und ist der **einzige**
Ort im gesamten Stack, der Zugriff auf den Docker-Socket hat. Das grosse Backend
bekommt niemals `docker.sock`; es ruft diesen Executor über eine token-geschützte
HTTP-API (siehe ``app.py``) auf.

Sicherheitsprinzip: Der Image-Name und **alle** ``docker run``-Flags sind hier
hartkodiert. Ein Aufrufer kann also kein beliebiges ``docker run`` auslösen,
sondern nur das feste, gehärtete Sandbox-Image mit fixen Limits starten.
"""

import asyncio
import logging
import os
import sys
import uuid
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("sandbox_executor")

SANDBOX_IMAGE = os.environ.get("TP_SANDBOX_IMAGE", "taskpilot-sandbox:latest")

# WICHTIG (Snap-Docker auf der GX10): Bind-Mount-Quellpfade werden vom Host-Daemon
# aufgelöst und müssen unter $HOME liegen. Der Executor-Container mountet dieses
# Verzeichnis PFADGLEICH (Host-Pfad == Container-Pfad), damit die an ``docker run -v``
# übergebenen Pfade auf dem Host existieren (Docker-out-of-Docker Sibling-Pattern).
OUTPUT_BASE = Path(
    os.environ.get(
        "TP_SANDBOX_OUTPUT_DIR",
        str(Path.home() / ".local" / "share" / "taskpilot" / "sandbox-output"),
    )
)

# Optionales, striktes Seccomp-Profil. Leer = Docker-Standard-Seccomp-Profil greift
# weiterhin (multi-arch, bewährt). Das mitgelieferte Profil ist strenger, aber
# architektur-sensibel; daher opt-in per Env.
SECCOMP_PROFILE = os.environ.get("TP_SANDBOX_SECCOMP", "").strip()

MAX_CODE_LENGTH = 50_000
MAX_TIMEOUT_SECONDS = 900


async def execute_in_sandbox(
    code: str,
    input_files: dict[str, str] | None = None,
    timeout_seconds: int = 300,
) -> dict:
    """Führt Python-Code in einem ephemeren, netzwerkisolierten Docker-Container aus.

    Gibt ein Ergebnis-Dict zurück, dessen Vertrag identisch zum bisherigen
    ``mcp-sandbox``-Verhalten ist (``success``, ``stdout``, ``stderr``,
    ``generated_files``, ``run_id``, ``duration_seconds`` …).
    """
    run_id = str(uuid.uuid4())[:8]
    container_name = f"tp-sandbox-{run_id}"

    work_dir = OUTPUT_BASE / run_id
    work_dir.mkdir(parents=True, exist_ok=True)

    input_dir = work_dir / "input"
    input_dir.mkdir(exist_ok=True)
    if input_files:
        for filename, content in input_files.items():
            safe_name = Path(filename).name
            (input_dir / safe_name).write_text(content, encoding="utf-8")

    output_dir = work_dir / "output"
    output_dir.mkdir(exist_ok=True)
    os.chmod(output_dir, 0o777)

    docker_args = [
        "docker", "run",
        "--rm", "-i",
        "--name", container_name,
        "--user", "0:0",
        "--network", "none",
        "--memory", "2g",
        "--cpus", "2",
        "--pids-limit", "50",
        "--cap-drop", "ALL",
        "--tmpfs", "/tmp:size=256m",
        "-v", f"{input_dir}:/input:ro",
        "-v", f"{output_dir}:/workspace:rw",
    ]
    # --no-new-privileges bleibt bewusst AUS: Kernel 6.17-nvidia (GX10) blockt
    # jede exec mit diesem Flag (siehe docker-compose.prod.yml).
    if SECCOMP_PROFILE and Path(SECCOMP_PROFILE).is_file():
        docker_args += ["--security-opt", f"seccomp={SECCOMP_PROFILE}"]
        logger.info("Seccomp-Profil aktiv: %s", SECCOMP_PROFILE)
    docker_args += ["--entrypoint", "python", SANDBOX_IMAGE, "-"]

    logger.info("Sandbox-Ausführung gestartet: run_id=%s, timeout=%ds", run_id, timeout_seconds)

    start_time = asyncio.get_event_loop().time()
    try:
        proc = await asyncio.create_subprocess_exec(
            *docker_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=code.encode("utf-8")), timeout=timeout_seconds
        )
    except asyncio.TimeoutError:
        logger.error("Sandbox Timeout nach %ds (run_id=%s)", timeout_seconds, run_id)
        try:
            killer = await asyncio.create_subprocess_exec(
                "docker", "kill", container_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await killer.wait()
        except Exception:
            pass
        return {
            "success": False,
            "error": f"Timeout: Code-Ausführung nach {timeout_seconds}s abgebrochen",
            "stdout": "",
            "stderr": "",
            "generated_files": [],
            "run_id": run_id,
            "duration_seconds": timeout_seconds,
        }
    except FileNotFoundError:
        logger.exception("docker-Binary nicht gefunden")
        return {
            "success": False,
            "error": "Docker nicht verfügbar (docker-CLI/Socket im Executor-Container fehlt)",
            "stdout": "",
            "stderr": "",
            "generated_files": [],
            "run_id": run_id,
            "duration_seconds": 0,
        }
    except Exception as e:
        logger.exception("Container-Fehler (run_id=%s)", run_id)
        return {
            "success": False,
            "error": f"Container-Fehler: {e}",
            "stdout": "",
            "stderr": "",
            "generated_files": [],
            "run_id": run_id,
            "duration_seconds": 0,
        }

    duration = asyncio.get_event_loop().time() - start_time

    generated_files = []
    if output_dir.exists():
        for f in output_dir.iterdir():
            if f.is_file() and f.name != "_script.py":
                generated_files.append({
                    "name": f.name,
                    "size_bytes": f.stat().st_size,
                    "path": str(f),
                })

    return {
        "success": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="replace")[-10000:],
        "stderr": stderr.decode("utf-8", errors="replace")[-5000:] if stderr else "",
        "generated_files": generated_files,
        "output_dir": str(output_dir),
        "run_id": run_id,
        "duration_seconds": round(duration, 2),
    }
