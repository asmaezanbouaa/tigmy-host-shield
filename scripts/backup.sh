#!/usr/bin/env bash
# Daily backup of the database + uploaded files (signatures, ID scans, PDFs).
# Keeps the last $KEEP backups in ./backups. Run from cron, e.g.:
#   15 3 * * * /opt/guest-registry/scripts/backup.sh >> /opt/guest-registry/backups/backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."

KEEP="${KEEP:-14}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
DB_FILE="${DB_FILE:-./data/guest_registry.db}"
STAMP="$(date +%Y-%m-%d_%H%M)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$BACKUP_DIR"

PYTHON=python3
[ -x .venv/bin/python ] && PYTHON=.venv/bin/python

# Consistent snapshot of SQLite even while the app is running
"$PYTHON" - "$DB_FILE" "$WORK/guest_registry.db" <<'EOF'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1])
dst = sqlite3.connect(sys.argv[2])
src.backup(dst)
dst.close()
src.close()
EOF

OUT="$BACKUP_DIR/tigmy-backup-$STAMP.tar.gz"
tar -czf "$OUT" \
  --exclude='./data/guest_registry.db*' \
  -C "$WORK" guest_registry.db \
  -C "$PWD" ./data
chmod 600 "$OUT"

# Delete old backups beyond $KEEP
ls -1t "$BACKUP_DIR"/tigmy-backup-*.tar.gz 2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm -f

echo "$(date -Is) backup written: $OUT ($(du -h "$OUT" | cut -f1))"
