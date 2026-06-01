#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Created .env from .env.example — review SECRET_KEY and ADMIN_PASSWORD."
fi

# Stop any old server still bound to the port (common cause of stale errors)
PORT="${PORT:-8000}"
if command -v fuser >/dev/null 2>&1; then
  fuser -k "${PORT}/tcp" 2>/dev/null || true
  sleep 1
fi

python scripts/migrate_v2.py
python scripts/init_db.py
alembic upgrade head 2>/dev/null || true

BASE_URL="$(grep -E '^BASE_URL=' .env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\r' || echo "http://localhost:${PORT}")"
BASE_URL="${BASE_URL:-http://localhost:${PORT}}"
echo ""
echo "============================================"
echo "  Tigmy Host Shield — guest link:  ${BASE_URL%/}/register"
echo "  Admin login:              ${BASE_URL%/}/admin/login"
echo "  Admin share + QR:         ${BASE_URL%/}/admin/share"
echo "  Set BASE_URL in .env when you deploy (see DEPLOY.md)"
echo "============================================"
echo ""
exec uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT}" --reload
