#!/bin/bash
# TaskPilot Sandbox Entrypoint
# Führt ein übergebenes Python-Script in der isolierten Umgebung aus.
# Das Script wird via stdin oder als Datei /workspace/_script.py übergeben.

set -euo pipefail

if [ -f "/workspace/_script.py" ]; then
    exec python /workspace/_script.py
elif [ -n "${SCRIPT_CONTENT:-}" ]; then
    echo "$SCRIPT_CONTENT" | exec python -
else
    echo "ERROR: Kein Script übergeben. Erwartet: /workspace/_script.py oder SCRIPT_CONTENT env var" >&2
    exit 1
fi
