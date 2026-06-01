#!/usr/bin/env bash
# Start app + free public URL (Cloudflare quick tunnel). Not for production — URL changes each restart.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

PORT="${PORT:-8000}"
mkdir -p bin
if [ ! -x bin/cloudflared ]; then
  echo "Downloading cloudflared..."
  curl -fsSL -o bin/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
  chmod +x bin/cloudflared
fi

fuser -k "${PORT}/tcp" 2>/dev/null || true
sleep 1

python scripts/migrate_v2.py 2>/dev/null || true
python scripts/init_db.py 2>/dev/null || true

nohup uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" > /tmp/guest-registry.log 2>&1 &
sleep 2

rm -f /tmp/cloudflared-guest.log
nohup ./bin/cloudflared tunnel --url "http://127.0.0.1:${PORT}" > /tmp/cloudflared-guest.log 2>&1 &
sleep 6

PUBLIC_URL=""
for _ in 1 2 3 4 5; do
  PUBLIC_URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/cloudflared-guest.log 2>/dev/null | head -1 || true)"
  [ -n "$PUBLIC_URL" ] && break
  sleep 2
done

if [ -z "$PUBLIC_URL" ]; then
  echo "Could not get public URL. See /tmp/cloudflared-guest.log"
  exit 1
fi

# Update BASE_URL in .env (keep other lines)
if grep -q '^BASE_URL=' .env 2>/dev/null; then
  sed -i "s|^BASE_URL=.*|BASE_URL=${PUBLIC_URL}|" .env
else
  echo "BASE_URL=${PUBLIC_URL}" >> .env
fi
if grep -q '^FORCE_HTTPS=' .env 2>/dev/null; then
  sed -i 's|^FORCE_HTTPS=.*|FORCE_HTTPS=true|' .env
else
  echo "FORCE_HTTPS=true" >> .env
fi

LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"

echo ""
echo "============================================"
echo "  Tigmy Host Shield — PUBLIC (share with guests):"
echo "    ${PUBLIC_URL}/register"
echo ""
echo "  Admin login:"
echo "    ${PUBLIC_URL}/admin/login"
echo ""
echo "  Same WiFi only (optional):"
echo "    http://${LAN_IP:-YOUR_IP}:${PORT}/register"
echo ""
echo "  Logs: /tmp/guest-registry.log  /tmp/cloudflared-guest.log"
echo "  Stop: fuser -k ${PORT}/tcp; pkill -f 'cloudflared tunnel'"
echo "============================================"
echo ""
echo "Updated .env BASE_URL to this public URL."
echo "Re-run this script after reboot (tunnel URL will change)."
echo "For a fixed tigmy-host-shield URL, see CUSTOM_URL.md (Render or your domain)."
