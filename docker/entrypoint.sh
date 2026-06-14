#!/bin/bash
set -e

# Upload-Verzeichnis: Docker named volumes werden als root erstellt,
# daher vor User-Switch Unterverzeichnisse anlegen und Ownership korrigieren
for d in /app/uploads /app/uploads/avatars /app/uploads/tasks /app/uploads/backgrounds /app/uploads/projects; do
    mkdir -p "$d"
done
chown -R taskpilot:taskpilot /app/uploads /tmp/taskpilot-exports 2>/dev/null || true

# Hermes-Home vorbereiten (als taskpilot). Die config.yaml wird zur Laufzeit
# vom Backend aus den Settings generiert (app.services.hermes_config). Hier nur
# das Verzeichnis-Skelett anlegen und Ownership sicherstellen — gemountete
# Assets (skills/, memories/, SOUL.md) bleiben erhalten.
gosu taskpilot bash -c '
    mkdir -p /home/taskpilot/.hermes/skills \
             /home/taskpilot/.hermes/memories \
             /home/taskpilot/.hermes/sessions \
             /home/taskpilot/.hermes/logs
'
chown -R taskpilot:taskpilot /home/taskpilot/.hermes 2>/dev/null || true

exec gosu taskpilot "$@"
