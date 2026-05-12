#!/bin/bash
set -e

# Nanobot-Config aus Template generieren (envsubst ersetzt $VAR-Platzhalter)
mkdir -p /home/taskpilot/.nanobot
envsubst < /app/nanobot-config.template.json > /home/taskpilot/.nanobot/config.json

exec "$@"
