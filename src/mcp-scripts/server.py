"""MCP-Server für Script-Orchestrierung (Schicht 1).

Verwaltet registrierte Scripts und führt sie in isolierten Docker-Containern aus.
Security-First: Nur deklarierte Scripts, nur deklarierte Secrets, nur deklarierte Netzwerk-Hosts.
"""

import asyncio
import json
import logging
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("mcp_scripts")

REGISTRY_PATH = Path(__file__).parent / "scripts.json"
SECRETS_DIR = Path(os.environ.get("TP_SECRETS_DIR", "/run/secrets"))
OUTPUT_BASE = Path(os.environ.get("TP_SCRIPTS_OUTPUT_DIR", "/tmp/taskpilot-scripts-output"))


def _load_registry() -> dict:
    """Script-Registry aus JSON laden."""
    with open(REGISTRY_PATH) as f:
        return json.load(f)


def _get_secret(name: str) -> str | None:
    """Secret aus Umgebungsvariable oder Secrets-Verzeichnis laden."""
    val = os.environ.get(name)
    if val:
        return val
    secret_file = SECRETS_DIR / name.lower()
    if secret_file.exists():
        return secret_file.read_text().strip()
    return None


async def _run_docker_container(
    script_config: dict,
    params: dict,
    input_dir: Path | None = None,
) -> dict:
    """Script in Docker-Container ausführen mit Security-Constraints."""
    security = script_config["security"]
    run_id = str(uuid.uuid4())[:8]
    container_name = f"tp-script-{script_config['id']}-{run_id}"

    output_dir = OUTPUT_BASE / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    docker_args = [
        "docker", "run",
        "--rm",
        "--name", container_name,
        "--no-new-privileges",
        "--security-opt", "no-new-privileges",
        "--cap-drop", "ALL",
        "--read-only",
        "--tmpfs", "/tmp:size=256m",
        "--memory", f"{security['memory_limit_mb']}m",
        "--cpus", str(security['cpu_cores']),
        "--pids-limit", "100",
        "-v", f"{output_dir}:/output:rw",
    ]

    if input_dir and input_dir.exists():
        docker_args.extend(["-v", f"{input_dir}:/input:ro"])

    network_allow = security.get("network_allow", [])
    llm_allow = security.get("llm_endpoints_allow", [])
    if not network_allow and not llm_allow:
        docker_args.extend(["--network", "none"])

    for secret_name in security.get("secrets_required", []):
        secret_val = _get_secret(secret_name)
        if secret_val:
            docker_args.extend(["-e", f"{secret_name}={secret_val}"])
        else:
            logger.warning("Secret %s nicht verfügbar für Script %s", secret_name, script_config["id"])

    for key, value in params.items():
        docker_args.extend(["-e", f"PARAM_{key.upper()}={value}"])

    docker_args.append(script_config["image"])

    timeout = security.get("max_timeout_seconds", 900)

    logger.info(
        "Starte Script %s (Container: %s, Timeout: %ds)",
        script_config["id"], container_name, timeout,
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            *docker_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.error("Script %s Timeout nach %ds", script_config["id"], timeout)
        await asyncio.create_subprocess_exec("docker", "kill", container_name)
        return {
            "success": False,
            "error": f"Timeout nach {timeout} Sekunden",
            "run_id": run_id,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Docker-Fehler: {str(e)}",
            "run_id": run_id,
        }

    output_files = []
    if output_dir.exists():
        output_files = [f.name for f in output_dir.iterdir() if f.is_file()]

    return {
        "success": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="replace")[-10000:],
        "stderr": stderr.decode("utf-8", errors="replace")[-5000:] if stderr else "",
        "output_files": output_files,
        "output_dir": str(output_dir),
        "run_id": run_id,
        "duration_hint": "Script wurde ausgeführt",
    }


TOOLS = [
    Tool(
        name="list_scripts",
        description="Alle registrierten Scripts mit ihren Parametern und Beschreibungen auflisten",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="run_script",
        description="Ein registriertes Script in einem isolierten Docker-Container ausführen. Nur registrierte Scripts sind erlaubt.",
        inputSchema={
            "type": "object",
            "properties": {
                "script_id": {
                    "type": "string",
                    "description": "ID des Scripts aus der Registry (z.B. 'toggl-rapport', 'md-to-word')",
                },
                "params": {
                    "type": "object",
                    "description": "Parameter als Key-Value-Paare gemäss Script-Definition",
                },
                "input_dir": {
                    "type": "string",
                    "description": "Optional: Pfad zu Input-Dateien die dem Script als /input gemountet werden",
                },
            },
            "required": ["script_id"],
        },
    ),
    Tool(
        name="get_script_info",
        description="Detailinformationen zu einem bestimmten Script (Parameter, Security-Config, Timeouts)",
        inputSchema={
            "type": "object",
            "properties": {
                "script_id": {"type": "string", "description": "ID des Scripts"},
            },
            "required": ["script_id"],
        },
    ),
]

server = Server("scripts")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    registry = _load_registry()

    if name == "list_scripts":
        scripts_summary = []
        for s in registry["scripts"]:
            scripts_summary.append({
                "id": s["id"],
                "name": s["name"],
                "description": s["description"],
                "params": s["params"],
                "autonomy": s["autonomy"],
                "timeout": s["security"]["max_timeout_seconds"],
                "data_class_max": s["security"]["data_class_max"],
            })
        return [TextContent(
            type="text",
            text=json.dumps(scripts_summary, indent=2, ensure_ascii=False),
        )]

    elif name == "get_script_info":
        script_id = arguments["script_id"]
        script = next((s for s in registry["scripts"] if s["id"] == script_id), None)
        if not script:
            return [TextContent(type="text", text=f"Script '{script_id}' nicht in Registry gefunden")]
        return [TextContent(
            type="text",
            text=json.dumps(script, indent=2, ensure_ascii=False),
        )]

    elif name == "run_script":
        script_id = arguments["script_id"]
        script = next((s for s in registry["scripts"] if s["id"] == script_id), None)
        if not script:
            available = [s["id"] for s in registry["scripts"]]
            return [TextContent(
                type="text",
                text=f"Script '{script_id}' nicht gefunden. Verfügbar: {available}",
            )]

        params = arguments.get("params", {})
        for p_def in script["params"]:
            if p_def["required"] and p_def["name"] not in params:
                return [TextContent(
                    type="text",
                    text=f"Pflicht-Parameter '{p_def['name']}' fehlt ({p_def['description']})",
                )]

        input_dir = None
        if arguments.get("input_dir"):
            input_dir = Path(arguments["input_dir"])
            if not input_dir.exists():
                return [TextContent(type="text", text=f"Input-Verzeichnis existiert nicht: {input_dir}")]

        logger.info("Script-Ausführung gestartet: %s mit params=%s", script_id, params)
        result = await _run_docker_container(script, params, input_dir)

        if result["success"]:
            output_text = f"Script '{script['name']}' erfolgreich ausgeführt.\n\n"
            if result["stdout"]:
                output_text += f"**Output:**\n```\n{result['stdout']}\n```\n\n"
            if result["output_files"]:
                output_text += f"**Erzeugte Dateien:** {', '.join(result['output_files'])}\n"
                output_text += f"**Output-Verzeichnis:** {result['output_dir']}\n"
        else:
            output_text = f"Script '{script['name']}' fehlgeschlagen.\n\n"
            output_text += f"**Fehler:** {result.get('error', 'Unbekannt')}\n"
            if result.get("stderr"):
                output_text += f"**Stderr:**\n```\n{result['stderr']}\n```\n"
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
