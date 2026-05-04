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

MDCONVERTER_SRC="${MDCONVERTER_PATH:-$HOME/dev/github/mdConverter}"
MD2POWERPOINT_SRC="${MD2POWERPOINT_PATH:-$HOME/dev/github/md2powerpoint}"

if [ ! -d "$MDCONVERTER_SRC" ]; then
    echo "FEHLER: mdConverter nicht gefunden unter $MDCONVERTER_SRC"
    echo "Setze MDCONVERTER_PATH auf den korrekten Pfad."
    exit 1
fi

if [ ! -d "$MD2POWERPOINT_SRC" ]; then
    echo "FEHLER: md2powerpoint nicht gefunden unter $MD2POWERPOINT_SRC"
    echo "Setze MD2POWERPOINT_PATH auf den korrekten Pfad."
    exit 1
fi

echo "  mdConverter:   $MDCONVERTER_SRC"
cp -r "$MDCONVERTER_SRC" "$VENDOR_DIR/mdconverter"

echo "  md2powerpoint: $MD2POWERPOINT_SRC"
cp -r "$MD2POWERPOINT_SRC" "$VENDOR_DIR/md2powerpoint"

# .git-Ordner entfernen (kein Git-History im Image)
rm -rf "$VENDOR_DIR/mdconverter/.git" "$VENDOR_DIR/md2powerpoint/.git"

echo "==> Vendor-Verzeichnis bereit."
echo ""
echo "Docker-Build starten mit:"
echo "  docker compose -f docker/docker-compose.prod.yml build"
