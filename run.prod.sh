#!/usr/bin/env bash
# Production start (no --reload). Use behind Caddy/nginx with HTTPS.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

if [ ! -f ".env" ]; then
  echo "Missing .env — copy .env.example and set BASE_URL, SECRET_KEY, ADMIN_PASSWORD, DEBUG=false"
  exit 1
fi

python scripts/migrate_v2.py
python scripts/init_db.py
alembic upgrade head 2>/dev/null || true
python scripts/migrate_v6.py 2>/dev/null || true

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
WORKERS="${WORKERS:-2}"

exec uvicorn app.main:app --host "$HOST" --port "$PORT" --workers "$WORKERS"
