#!/bin/bash
set -e

# Upload-Verzeichnis: Docker named volumes werden als root erstellt,
# daher vor User-Switch Unterverzeichnisse anlegen und Ownership korrigieren
for d in /app/uploads /app/uploads/avatars /app/uploads/tasks /app/uploads/backgrounds /app/uploads/projects; do
    mkdir -p "$d"
done
chown -R taskpilot:taskpilot /app/uploads /tmp/taskpilot-exports 2>/dev/null || true

# Nanobot-Config aus Template generieren (als taskpilot)
gosu taskpilot bash -c '
    mkdir -p /home/taskpilot/.nanobot
    envsubst < /app/nanobot-config.template.json > /home/taskpilot/.nanobot/config.json
'

exec gosu taskpilot "$@"
