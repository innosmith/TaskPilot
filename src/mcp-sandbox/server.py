"""MCP-Server für Code-Sandbox-Execution (Schicht 2).

Generierter Python-Code wird in einem ephemeren, netzwerkisolierten Docker-Container
ausgeführt. Security-First: Kein Netzwerk, keine Secrets, begrenzter Speicher/CPU.
"""

import asyncio
import json
import logging
import os
import sys
import tempfile
import uuid
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("mcp_sandbox")

SANDBOX_IMAGE = os.environ.get("TP_SANDBOX_IMAGE", "taskpilot-sandbox:latest")
OUTPUT_BASE = Path(os.environ.get("TP_SANDBOX_OUTPUT_DIR", "/tmp/taskpilot-sandbox-output"))
SECCOMP_PROFILE = Path(__file__).parent.parent.parent / "docker" / "sandbox" / "seccomp-profile.json"
MAX_CODE_LENGTH = 50_000
MAX_OUTPUT_SIZE = 500 * 1024 * 1024  # 500 MB

BLOCKED_IMPORTS = [
    "subprocess", "os.system", "shutil.rmtree",
    "ctypes", "importlib", "pickle",
]

BLOCKED_PATTERNS = [
    "exec(", "eval(", "compile(",
    "__import__", "os.system", "subprocess",
    "open('/etc", "open('/proc", "open('/sys",
    "os.environ", "os.getenv",
]


def _validate_code(code: str) -> list[str]:
    """Prüft Code auf offensichtlich gefährliche Patterns (Defence-in-Depth, nicht alleiniger Schutz)."""
    warnings = []
    for pattern in BLOCKED_PATTERNS:
        if pattern in code:
            warnings.append(f"Verdächtiges Pattern gefunden: '{pattern}'")
    return warnings


async def _execute_in_sandbox(
    code: str,
    input_files: dict[str, str] | None = None,
    timeout_seconds: int = 300,
) -> dict:
    """Code in isoliertem Docker-Container ausführen."""
    run_id = str(uuid.uuid4())[:8]
    container_name = f"tp-sandbox-{run_id}"

    work_dir = OUTPUT_BASE / run_id
    work_dir.mkdir(parents=True, exist_ok=True)

    script_path = work_dir / "_script.py"
    script_path.write_text(code, encoding="utf-8")

    input_dir = work_dir / "input"
    input_dir.mkdir(exist_ok=True)
    if input_files:
        for filename, content in input_files.items():
            safe_name = Path(filename).name
            (input_dir / safe_name).write_text(content, encoding="utf-8")

    output_dir = work_dir / "output"
    output_dir.mkdir(exist_ok=True)
    os.chmod(output_dir, 0o777)

    seccomp_arg = []
    if SECCOMP_PROFILE.exists():
        seccomp_arg = ["--security-opt", f"seccomp={SECCOMP_PROFILE}"]

    docker_args = [
        "docker", "run",
        "--rm", "-i",
        "--name", container_name,
        "--user", "0:0",
        "--network", "none",
        "--memory", "2g",
        "--cpus", "2",
        "--pids-limit", "50",
        "--tmpfs", "/tmp:size=256m",
        *seccomp_arg,
        "-v", f"{input_dir}:/input:ro",
        "-v", f"{output_dir}:/workspace:rw",
        "--entrypoint", "python",
        SANDBOX_IMAGE, "-",
    ]

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
            await asyncio.create_subprocess_exec("docker", "kill", container_name)
        except Exception:
            pass
        return {
            "success": False,
            "error": f"Timeout: Code-Ausführung nach {timeout_seconds}s abgebrochen",
            "run_id": run_id,
            "duration_seconds": timeout_seconds,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Container-Fehler: {str(e)}",
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


TOOLS = [
    Tool(
        name="execute_code",
        description=(
            "Python-Code in einer isolierten Sandbox ausführen. "
            "Die Sandbox hat KEIN Netzwerk, KEINE Secrets und begrenzte Ressourcen. "
            "Verfügbare Packages: pandas, numpy, matplotlib, seaborn, openpyxl, scipy, pyyaml, jinja2, tabulate. "
            "Input-Dateien werden in /input/ bereitgestellt (read-only). "
            "Output-Dateien in /workspace/ schreiben."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python-Code der ausgeführt werden soll",
                },
                "input_files": {
                    "type": "object",
                    "description": "Optional: Dict von {filename: content} die als /input/filename verfügbar gemacht werden",
                    "additionalProperties": {"type": "string"},
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Timeout in Sekunden (default: 300, max: 900)",
                    "default": 300,
                },
                "description": {
                    "type": "string",
                    "description": "Kurzbeschreibung was der Code tut (für Audit-Log)",
                },
            },
            "required": ["code"],
        },
    ),
    Tool(
        name="list_packages",
        description="Zeigt alle vorinstallierten Python-Packages im Sandbox-Container",
        inputSchema={"type": "object", "properties": {}},
    ),
]

AVAILABLE_PACKAGES = [
    "pandas 2.2.3", "numpy 2.1.3", "openpyxl 3.1.5", "xlsxwriter 3.2.0",
    "matplotlib 3.9.3", "seaborn 0.13.2", "pyyaml 6.0.2", "toml 0.10.2",
    "python-dateutil 2.9.0", "chardet 5.2.0", "regex 2024.11.6",
    "tabulate 0.9.0", "jinja2 3.1.4", "scipy 1.14.1",
]

server = Server("sandbox")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "list_packages":
        return [TextContent(
            type="text",
            text="Verfügbare Packages in der Sandbox:\n" + "\n".join(f"- {p}" for p in AVAILABLE_PACKAGES),
        )]

    elif name == "execute_code":
        code = arguments.get("code", "").strip()
        if not code:
            return [TextContent(type="text", text="Fehler: Kein Code übergeben")]

        if len(code) > MAX_CODE_LENGTH:
            return [TextContent(type="text", text=f"Fehler: Code zu lang ({len(code)} Zeichen, max {MAX_CODE_LENGTH})")]

        warnings = _validate_code(code)
        if warnings:
            warning_text = "**Sicherheits-Warnungen (Code wird trotzdem ausgeführt, Sandbox schützt):**\n"
            warning_text += "\n".join(f"- {w}" for w in warnings)
            logger.warning("Code-Warnungen für Sandbox-Ausführung: %s", warnings)

        timeout = min(arguments.get("timeout_seconds", 300), 900)
        input_files = arguments.get("input_files")
        description = arguments.get("description", "Keine Beschreibung")

        logger.info("Sandbox execute_code: description='%s', code_length=%d", description, len(code))

        result = await _execute_in_sandbox(code, input_files, timeout)

        output_text = ""
        if warnings:
            output_text += "**Sicherheits-Hinweise:**\n" + "\n".join(f"- {w}" for w in warnings) + "\n\n"

        if result["success"]:
            output_text += f"**Ausführung erfolgreich** (Dauer: {result['duration_seconds']}s)\n\n"
            if result["stdout"]:
                output_text += f"**Output:**\n```\n{result['stdout']}\n```\n\n"
            if result["generated_files"]:
                output_text += "**Erzeugte Dateien:**\n"
                for f in result["generated_files"]:
                    size_kb = f["size_bytes"] / 1024
                    output_text += f"- {f['name']} ({size_kb:.1f} KB) → `{f['path']}`\n"
        else:
            output_text += f"**Ausführung fehlgeschlagen** (Exit-Code: {result.get('exit_code', '?')})\n\n"
            if result.get("error"):
                output_text += f"**Fehler:** {result['error']}\n\n"
            if result.get("stderr"):
                output_text += f"**Stderr:**\n```\n{result['stderr']}\n```\n\n"
            if result.get("stdout"):
                output_text += f"**Stdout:**\n```\n{result['stdout']}\n```\n"

        return [TextContent(type="text", text=output_text)]

    return [TextContent(type="text", text=f"Unbekanntes Tool: {name}")]


async def main():
    OUTPUT_BASE.mkdir(parents=True, exist_ok=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
