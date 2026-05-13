#!/usr/bin/env bash
# TaskPilot Produktions-Backup
#
# Sichert alle produktionsrelevanten Daten auf OneDrive:
#   - PostgreSQL-Datenbank (pg_dump)
#   - Uploads (Task-Attachments, Avatare, Icons)
#   - Nanobot-Workspace (Skills, Memory, Sessions)
#   - Konfigurationsdateien (.env.prod, nanobot-config, secrets)
#
# Voraussetzung: Prod-Container laufen (make prod)
# Aufruf: ./scripts/backup-prod.sh  oder  make backup-prod

set -euo pipefail

# ── Konfiguration ────────────────────────────────────────────────────────────

BACKUP_BASE="${BACKUP_BASE:-${HOME}/OneDrive/Backup/TaskPilot}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

PROD_DB_CONTAINER="taskpilot-postgres-prod"
PROD_BACKEND_CONTAINER="taskpilot-backend-prod"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NANOBOT_CONFIG="${HOME}/.nanobot/config.json"
NANOBOT_WORKSPACE="${HOME}/.nanobot/workspace"
SECRETS_DIR="${HOME}/.secrets/taskpilot"

TIMESTAMP="$(date +%Y-%m-%d_%H%M%S)"
BACKUP_DIR="${BACKUP_BASE}/${TIMESTAMP}"

# ── Hilfsfunktionen ─────────────────────────────────────────────────────────

if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' BOLD='' NC=''
fi

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "\n${BOLD}── $* ──${NC}"; }

cleanup() {
    if [[ $? -ne 0 ]]; then
        log_error "Backup fehlgeschlagen! Unvollstaendiges Backup unter: ${BACKUP_DIR}"
        log_error "Bitte manuell pruefen und ggf. loeschen."
    fi
}
trap cleanup EXIT

# ── Voraussetzungen pruefen ──────────────────────────────────────────────────

log_step "Voraussetzungen pruefen"

if ! docker ps --format '{{.Names}}' | grep -q "^${PROD_DB_CONTAINER}$"; then
    log_error "Container '${PROD_DB_CONTAINER}' laeuft nicht. Starte Prod zuerst mit: make prod"
    exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -q "^${PROD_BACKEND_CONTAINER}$"; then
    log_warn "Container '${PROD_BACKEND_CONTAINER}' laeuft nicht. Uploads werden uebersprungen."
    SKIP_UPLOADS=true
else
    SKIP_UPLOADS=false
fi

mkdir -p "${BACKUP_DIR}/config"
log_info "Backup-Verzeichnis: ${BACKUP_DIR}"

START_TIME=$(date +%s)

# ── 1. PostgreSQL-Dump ───────────────────────────────────────────────────────

log_step "1/5 PostgreSQL-Dump"

DB_USER=$(docker exec "${PROD_DB_CONTAINER}" bash -c 'echo $POSTGRES_USER')
DB_NAME=$(docker exec "${PROD_DB_CONTAINER}" bash -c 'echo $POSTGRES_DB')

log_info "Datenbank: ${DB_NAME} (User: ${DB_USER})"

docker exec "${PROD_DB_CONTAINER}" \
    pg_dump -U "${DB_USER}" -d "${DB_NAME}" \
        --clean --if-exists --no-owner --no-privileges \
    | gzip > "${BACKUP_DIR}/taskpilot_prod.sql.gz"

DB_SIZE=$(du -h "${BACKUP_DIR}/taskpilot_prod.sql.gz" | cut -f1)
log_info "DB-Dump erstellt: ${DB_SIZE}"

# ── 2. Uploads sichern ──────────────────────────────────────────────────────

log_step "2/5 Uploads sichern"

if [[ "${SKIP_UPLOADS}" == "false" ]]; then
    UPLOADS_TMP=$(mktemp -d)
    docker cp "${PROD_BACKEND_CONTAINER}:/app/uploads" "${UPLOADS_TMP}/uploads" 2>/dev/null || true

    if [[ -d "${UPLOADS_TMP}/uploads" ]] && [[ -n "$(ls -A "${UPLOADS_TMP}/uploads" 2>/dev/null)" ]]; then
        tar -czf "${BACKUP_DIR}/uploads.tar.gz" -C "${UPLOADS_TMP}" uploads
        UPLOADS_SIZE=$(du -h "${BACKUP_DIR}/uploads.tar.gz" | cut -f1)
        log_info "Uploads gesichert: ${UPLOADS_SIZE}"
    else
        log_warn "Keine Uploads vorhanden, uebersprungen."
    fi

    rm -rf "${UPLOADS_TMP}"
else
    log_warn "Backend-Container nicht verfuegbar, Uploads uebersprungen."
fi

# ── 3. Nanobot-Workspace sichern ────────────────────────────────────────────

log_step "3/5 Nanobot-Workspace sichern"

if [[ -d "${NANOBOT_WORKSPACE}" ]]; then
    tar -czf "${BACKUP_DIR}/nanobot-workspace.tar.gz" \
        -C "$(dirname "${NANOBOT_WORKSPACE}")" \
        "$(basename "${NANOBOT_WORKSPACE}")"
    WS_SIZE=$(du -h "${BACKUP_DIR}/nanobot-workspace.tar.gz" | cut -f1)
    log_info "Nanobot-Workspace gesichert: ${WS_SIZE}"
else
    log_warn "Nanobot-Workspace nicht gefunden unter ${NANOBOT_WORKSPACE}"
fi

# ── 4. Konfigurationsdateien kopieren ────────────────────────────────────────

log_step "4/5 Konfigurationsdateien sichern"

if [[ -f "${PROJECT_ROOT}/.env.prod" ]]; then
    cp "${PROJECT_ROOT}/.env.prod" "${BACKUP_DIR}/config/env.prod"
    log_info ".env.prod gesichert"
else
    log_warn ".env.prod nicht gefunden unter ${PROJECT_ROOT}/.env.prod"
fi

if [[ -f "${NANOBOT_CONFIG}" ]]; then
    cp "${NANOBOT_CONFIG}" "${BACKUP_DIR}/config/nanobot-config.json"
    log_info "nanobot-config.json gesichert"
else
    log_warn "Nanobot-Config nicht gefunden unter ${NANOBOT_CONFIG}"
fi

if [[ -d "${SECRETS_DIR}" ]]; then
    cp -r "${SECRETS_DIR}" "${BACKUP_DIR}/config/secrets"
    log_info "Secrets-Verzeichnis gesichert"
else
    log_info "Kein Secrets-Verzeichnis unter ${SECRETS_DIR} (optional)"
fi

# ── 5. Integritaets-Log ─────────────────────────────────────────────────────

log_step "5/5 Integritaets-Log erstellen"

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

{
    echo "TaskPilot Backup"
    echo "================"
    echo ""
    echo "Timestamp:  ${TIMESTAMP}"
    echo "Host:       $(hostname)"
    echo "Dauer:      ${DURATION}s"
    echo "Ziel:       ${BACKUP_DIR}"
    echo ""
    echo "Dateien:"
    echo "--------"
    for f in "${BACKUP_DIR}"/*.{sql.gz,tar.gz} "${BACKUP_DIR}"/config/*; do
        [[ -e "$f" ]] || continue
        SIZE=$(du -h "$f" | cut -f1)
        HASH=$(sha256sum "$f" | cut -d' ' -f1)
        REL=$(basename "$f")
        printf "  %-35s %8s  sha256:%s\n" "$REL" "$SIZE" "$HASH"
    done
} > "${BACKUP_DIR}/backup.log"

log_info "Backup-Log geschrieben"

# ── 6. Retention (alte Backups entfernen) ────────────────────────────────────

if [[ "${RETENTION_DAYS}" -gt 0 ]]; then
    OLD_COUNT=$(find "${BACKUP_BASE}" -maxdepth 1 -mindepth 1 -type d -mtime "+${RETENTION_DAYS}" 2>/dev/null | wc -l)
    if [[ "${OLD_COUNT}" -gt 0 ]]; then
        log_step "Retention: ${OLD_COUNT} Backup(s) aelter als ${RETENTION_DAYS} Tage entfernen"
        find "${BACKUP_BASE}" -maxdepth 1 -mindepth 1 -type d -mtime "+${RETENTION_DAYS}" -exec rm -rf {} \;
        log_info "${OLD_COUNT} alte Backup(s) entfernt"
    fi
fi

# ── Zusammenfassung ──────────────────────────────────────────────────────────

TOTAL_SIZE=$(du -sh "${BACKUP_DIR}" | cut -f1)

echo ""
echo -e "${GREEN}${BOLD}Backup erfolgreich abgeschlossen${NC}"
echo -e "  Verzeichnis:  ${BACKUP_DIR}"
echo -e "  Gesamtgroesse: ${TOTAL_SIZE}"
echo -e "  Dauer:        ${DURATION}s"
echo ""
cat "${BACKUP_DIR}/backup.log"
