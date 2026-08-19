#!/bin/bash
# /usr/local/bin/shopm-backup.sh
# Backup quotidien PostgreSQL → Backblaze B2

set -uo pipefail

# ── Configuration ─────────────────────────────────────────────────
ENV_FILE="/var/www/shopm/backend/.env"
BACKUP_DIR="/var/backups/shopm"
B2_REMOTE="backblaze"
B2_BUCKET="shopm-backups"
B2_PREFIX="db"
LOCAL_KEEP_DAYS=3
LOG_FILE="/var/log/shopm-backup.log"
ADMIN_EMAIL="abdelfadelsaliou@gmail.com"

TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_FILE="${BACKUP_DIR}/shopm_${TIMESTAMP}.sql.gz"

# ── Helpers ───────────────────────────────────────────────────────
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

# Lire une variable depuis le fichier .env
env_var() { grep -E "^${1}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d'=' -f2- | tr -d '"'"'"' '; }

send_failure_email() {
  local error_msg="$1"
  local smtp_host smtp_port smtp_user smtp_pass
  smtp_host=$(env_var EMAIL_HOST)
  smtp_port=$(env_var EMAIL_PORT)
  smtp_user=$(env_var EMAIL_HOST_USER)
  smtp_pass=$(env_var EMAIL_HOST_PASSWORD)

  [[ -z "$smtp_host" || -z "$smtp_user" ]] && return 1

  python3 - <<PYEOF
import smtplib
from email.mime.text import MIMEText

body = """Bonjour,

Le backup automatique de ShopM a échoué.

Date  : $(date '+%Y-%m-%d à %H:%M')
Erreur: ${error_msg}

Consultez le journal : /var/log/shopm-backup.log

-- ShopM Backup Monitor (Hetzner VPS)
"""
msg = MIMEText(body, 'plain', 'utf-8')
msg['Subject'] = '[ShopM] ALERTE — Backup base de données échoué'
msg['From'] = '${smtp_user}'
msg['To'] = '${ADMIN_EMAIL}'

port = int('${smtp_port}' or 587)
with smtplib.SMTP('${smtp_host}', port) as s:
    s.ehlo()
    s.starttls()
    s.login('${smtp_user}', '${smtp_pass}')
    s.sendmail('${smtp_user}', ['${ADMIN_EMAIL}'], msg.as_string())
print("Email envoyé")
PYEOF
}

on_error() {
  local line=$1 code=$2
  log "ERREUR à la ligne ${line} (code retour: ${code})"
  send_failure_email "Ligne ${line}, code ${code}" 2>/dev/null \
    || log "Impossible d'envoyer l'email d'alerte (SMTP non configuré ?)"
  exit 1
}

trap 'on_error $LINENO $?' ERR

# ── Lecture credentials DB ────────────────────────────────────────
DB_URL=$(env_var DATABASE_URL)

if [[ -n "$DB_URL" ]]; then
  # Format postgresql://user:pass@host:port/dbname
  DB_USER=$(echo "$DB_URL" | sed -E 's|.*://([^:@]*)(:.*)?@.*|\1|')
  DB_PASS=$(echo "$DB_URL" | sed -E 's|.*://[^:]*:([^@]*)@.*|\1|')
  DB_HOST=$(echo "$DB_URL" | sed -E 's|.*@([^:/]*).*|\1|')
  DB_PORT=$(echo "$DB_URL" | sed -E 's|.*:([0-9]+)/.*|\1|')
  DB_NAME=$(echo "$DB_URL" | sed -E 's|.*/([^?]+).*|\1|')
else
  DB_USER=$(env_var DB_USER)
  DB_PASS=$(env_var DB_PASSWORD)
  DB_HOST=$(env_var DB_HOST)
  DB_PORT=$(env_var DB_PORT)
  DB_NAME=$(env_var DB_NAME)
fi

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

# ── Backup ───────────────────────────────────────────────────────
log "══════════════════════════════════════════"
log "Démarrage backup ShopM"
log "Base     : ${DB_NAME}@${DB_HOST}:${DB_PORT}"
log "Fichier  : ${BACKUP_FILE}"

mkdir -p "$BACKUP_DIR"

log "Dump PostgreSQL en cours..."
PGPASSWORD="$DB_PASS" pg_dump \
  -U "$DB_USER" \
  -h "$DB_HOST" \
  -p "$DB_PORT" \
  --no-password \
  "$DB_NAME" | gzip > "$BACKUP_FILE"

SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
log "Dump OK : ${SIZE}"

# ── Upload B2 ────────────────────────────────────────────────────
log "Upload vers Backblaze B2..."
rclone copy "$BACKUP_FILE" "${B2_REMOTE}:${B2_BUCKET}/${B2_PREFIX}/" \
  --log-level ERROR \
  --retries 3

log "Upload OK ✓"

# Supprimer les anciens backups B2 (> 7 jours)
rclone delete "${B2_REMOTE}:${B2_BUCKET}/${B2_PREFIX}/" \
  --min-age 7d \
  --log-level ERROR 2>/dev/null || true

# ── Nettoyage local ──────────────────────────────────────────────
find "$BACKUP_DIR" -name "shopm_*.sql.gz" -mtime "+${LOCAL_KEEP_DAYS}" -delete
log "Nettoyage local : > ${LOCAL_KEEP_DAYS} jours supprimés"

log "Backup terminé avec succès ✓"
log "══════════════════════════════════════════"
