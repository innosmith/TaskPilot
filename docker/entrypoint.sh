#!/bin/bash
set -e

# Nanobot-Config aus Template generieren (envsubst ersetzt $VAR-Platzhalter)
mkdir -p /root/.nanobot
envsubst < /app/nanobot-config.template.json > /root/.nanobot/config.json

exec "$@"
