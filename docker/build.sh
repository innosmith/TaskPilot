#!/usr/bin/env bash
# Build-Script: Bereitet den Docker-Build-Kontext vor und baut Images.
# Kopiert private Packages in vendor/, damit sie ohne Git-Credentials
# im Docker-Image installiert werden koennen.
#
# Aufruf:
#   ./docker/build.sh          # Nur vendor vorbereiten
#   ./docker/build.sh --all    # vendor + alle Images bauen

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/.."
VENDOR_DIR="$PROJECT_ROOT/src/backend/vendor"

echo "==> Vendor-Verzeichnis vorbereiten..."
rm -rf "$VENDOR_DIR"
mkdir -p "$VENDOR_DIR"

CONTENTCONVERTER_SRC="${CONTENTCONVERTER_PATH:-$HOME/dev/github/contentConverter}"

if [ ! -d "$CONTENTCONVERTER_SRC" ]; then
    echo "FEHLER: contentConverter nicht gefunden unter $CONTENTCONVERTER_SRC"
    echo "Setze CONTENTCONVERTER_PATH auf den korrekten Pfad."
    exit 1
fi

echo "  contentConverter: $CONTENTCONVERTER_SRC"
cp -r "$CONTENTCONVERTER_SRC" "$VENDOR_DIR/contentconverter"
rm -rf "$VENDOR_DIR/contentconverter/.git"

echo "==> Vendor-Verzeichnis bereit."

# Sandbox-Image bauen (falls Dockerfile vorhanden)
if [ -f "$SCRIPT_DIR/sandbox/Dockerfile" ]; then
    echo ""
    echo "==> Sandbox-Image bauen..."
    docker build -t taskpilot-sandbox:latest "$SCRIPT_DIR/sandbox/"
fi

if [ "${1:-}" = "--all" ]; then
    echo ""
    echo "==> Integration-Images bauen..."
    docker compose -f "$SCRIPT_DIR/docker-compose.yml" \
        -f "$SCRIPT_DIR/docker-compose.integration.yml" build

    echo ""
    echo "==> Produktion-Images bauen..."
    docker compose -f "$SCRIPT_DIR/docker-compose.prod.yml" build

    echo ""
    echo "==> Alle Images gebaut."
else
    echo ""
    echo "Naechste Schritte:"
    echo "  make int    # Integration starten"
    echo "  make prod   # Produktion starten"
    echo "  make build  # Alle Images bauen (ohne Start)"
fi
