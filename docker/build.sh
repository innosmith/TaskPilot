#!/usr/bin/env bash
# Build-Script: Bereitet den Docker-Build-Kontext vor.
# Kopiert private Packages in vendor/, damit sie ohne Git-Credentials
# im Docker-Image installiert werden können.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/../src/backend"
VENDOR_DIR="$BACKEND_DIR/vendor"

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

# .git-Ordner entfernen (kein Git-History im Image)
rm -rf "$VENDOR_DIR/contentconverter/.git"

echo "==> Vendor-Verzeichnis bereit."
echo ""
echo "Docker-Build starten mit:"
echo "  docker compose -f docker/docker-compose.prod.yml build"
