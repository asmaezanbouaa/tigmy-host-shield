#!/usr/bin/env bash
# Run the app in production mode on this computer with a free public HTTPS link
# (Cloudflare quick tunnel). The link changes each time this script is started.
# Keep this terminal open — closing it (or the computer sleeping) takes the site offline.
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"
LOG_DIR="./data/logs"
mkdir -p "$LOG_DIR"

if [ ! -x .venv/bin/uvicorn ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
if [ ! -f .env ]; then
  echo "Missing .env — copy .env.example and set production values first."
  exit 1
fi
if [ ! -x bin/cloudflared ]; then
  mkdir -p bin
  curl -fsSL -o bin/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
  chmod +x bin/cloudflared
fi

# Stop anything left over from a previous run
fuser -k "${PORT}/tcp" 2>/dev/null || true
pkill -f "cloudflared tunnel --url http://127.0.0.1:${PORT}" 2>/dev/null || true
sleep 1

cleanup() {
  [ -n "${TUNNEL_PID:-}" ] && kill "$TUNNEL_PID" 2>/dev/null || true
}
trap cleanup EXIT

# 1. Open the tunnel first so the app starts with the right public URL
: > "$LOG_DIR/cloudflared.log"
./bin/cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:${PORT}" >> "$LOG_DIR/cloudflared.log" 2>&1 &
TUNNEL_PID=$!

PUBLIC_URL=""
for _ in $(seq 1 30); do
  PUBLIC_URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG_DIR/cloudflared.log" | head -1 || true)"
  [ -n "$PUBLIC_URL" ] && break
  sleep 1
done
if [ -z "$PUBLIC_URL" ]; then
  echo "Could not get a public URL. See $LOG_DIR/cloudflared.log"
  exit 1
fi

sed -i "s|^BASE_URL=.*|BASE_URL=${PUBLIC_URL}|" .env

# 2. Back up existing data, prepare the database
[ -f data/guest_registry.db ] && ./scripts/backup.sh || true
.venv/bin/python scripts/run_all_migrations.py >/dev/null
.venv/bin/python scripts/init_db.py >/dev/null

echo ""
echo "============================================"
echo "  Tigmy Host Shield is LIVE"
echo ""
echo "  Guest link (share this):  ${PUBLIC_URL}/register"
echo "  Admin login:              ${PUBLIC_URL}/admin/login"
echo "  Share page + QR code:     ${PUBLIC_URL}/admin/share"
echo ""
echo "  Admin username/password: see ADMIN_USERNAME / ADMIN_PASSWORD in .env"
echo "  Keep this window open. Ctrl+C stops the site."
echo "============================================"
echo ""

# 3. Run the app (one worker: SQLite + in-memory rate limits).
# If the app process is stopped on its own (e.g. to load an update), it restarts
# and the public link stays the same:  ./scripts/restart-app.sh
while true; do
  # "|| true": an app exit must not end this script (set -e), or the public link would close too
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --workers 1 2>&1 | tee -a "$LOG_DIR/app.log" || true
  echo "App stopped. Restarting in 2 seconds (press Ctrl+C to stop the site)..."
  sleep 2
done
