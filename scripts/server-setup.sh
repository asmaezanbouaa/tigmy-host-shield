#!/usr/bin/env bash
# One-command production setup on a fresh Ubuntu 22.04/24.04 server (e.g. Oracle Cloud Always Free).
#
#   git clone https://github.com/asmaezanbouaa/tigmy-host-shield.git && cd tigmy-host-shield
#   DOMAIN=tigmi.duckdns.org ./scripts/server-setup.sh
#
# Optional: IMPORT=~/tigmy-backup-XXXX.tar.gz  restores data made with scripts/backup.sh (database + files).
# Safe to run again (e.g. after `git pull`): it keeps the existing .env and data.
set -euo pipefail
cd "$(dirname "$0")/.."
APP_DIR="$(pwd)"
APP_USER="$(id -un)"

DOMAIN="${DOMAIN:-}"
if [ -z "$DOMAIN" ]; then
  read -rp "Your site address (e.g. tigmi.duckdns.org): " DOMAIN
fi
DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN#http://}"; DOMAIN="${DOMAIN%%/*}"
[ -n "$DOMAIN" ] || { echo "A domain is required."; exit 1; }

step() { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }

step "System packages"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  python3 python3-venv python3-pip git caddy sqlite3 \
  tesseract-ocr tesseract-ocr-eng tesseract-ocr-fra \
  unattended-upgrades fail2ban iptables-persistent >/dev/null

step "Automatic security updates and SSH brute-force protection"
sudo dpkg-reconfigure -f noninteractive unattended-upgrades >/dev/null 2>&1 || true
sudo systemctl enable --now fail2ban >/dev/null 2>&1 || true

step "Firewall: only SSH, HTTP and HTTPS"
# Oracle's Ubuntu images block web ports in iptables; open 80/443 (idempotent)
# The rules must come BEFORE the image's final REJECT rule, or they never apply.
for port in 80 443; do
  while sudo iptables -D INPUT -p tcp --dport "$port" -m state --state NEW -j ACCEPT 2>/dev/null; do :; done
done
REJECT_POS="$(sudo iptables -L INPUT --line-numbers -n | awk '/REJECT/ {print $1; exit}')"
for port in 443 80; do
  sudo iptables -I INPUT "${REJECT_POS:-1}" -p tcp --dport "$port" -m state --state NEW -j ACCEPT
done
sudo netfilter-persistent save >/dev/null 2>&1 || true

if [ "$(awk '/MemTotal/ {print $2}' /proc/meminfo)" -lt 1800000 ] && [ ! -f /swapfile ]; then
  step "Adding 2 GB swap (small server)"
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

step "Python environment"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

if [ -n "${IMPORT:-}" ]; then
  step "Importing your data from $IMPORT"
  [ -f "$IMPORT" ] || { echo "Backup not found: $IMPORT"; exit 1; }
  TMP="$(mktemp -d)"
  tar -xzf "$IMPORT" -C "$TMP"
  mkdir -p data
  [ -d "$TMP/data" ] && cp -a "$TMP/data/." data/
  [ -d "$TMP/storage" ] && mkdir -p storage && cp -a "$TMP/storage/." storage/
  cp "$TMP/guest_registry.db" data/guest_registry.db
  rm -rf "$TMP" data/logs
  echo "Imported database and files."
fi

if [ ! -f .env ]; then
  step "Production settings (.env)"
  read -rp "Admin username: " ADMIN_USER
  while true; do
    read -rsp "Admin password (12+ characters, not the username): " ADMIN_PASS; echo
    if [ "${#ADMIN_PASS}" -ge 12 ] && [ "$ADMIN_PASS" != "$ADMIN_USER" ]; then break; fi
    echo "Too weak, try again."
  done
  SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  cp .env.example .env
  sed -i \
    -e "s|^APP_ENV=.*|APP_ENV=production|" \
    -e "s|^DEBUG=.*|DEBUG=false|" \
    -e "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET}|" \
    -e "s|^BASE_URL=.*|BASE_URL=https://${DOMAIN}|" \
    -e "s|^FORCE_HTTPS=.*|FORCE_HTTPS=true|" \
    -e "s|^HOST=.*|HOST=127.0.0.1|" \
    -e "s|^DATABASE_URL=.*|DATABASE_URL=sqlite:///./data/guest_registry.db|" \
    -e "s|^STORAGE_PATH=.*|STORAGE_PATH=./storage|" \
    -e "s|^AI_PROVIDER=.*|AI_PROVIDER=local|" \
    -e "s|^ADMIN_USERNAME=.*|ADMIN_USERNAME=${ADMIN_USER}|" \
    .env
  # password may contain characters sed would misread, so write it with Python
  ADMIN_PASS="$ADMIN_PASS" python3 - <<'PY'
import os, re
p = ".env"; s = open(p).read()
s = re.sub(r"^ADMIN_PASSWORD=.*$", "ADMIN_PASSWORD=" + os.environ["ADMIN_PASS"], s, flags=re.M)
open(p, "w").write(s)
PY
  chmod 600 .env
else
  step "Keeping existing .env (updating the site address)"
  sed -i "s|^BASE_URL=.*|BASE_URL=https://${DOMAIN}|; s|^FORCE_HTTPS=.*|FORCE_HTTPS=true|" .env
fi

step "Database"
mkdir -p data storage backups
.venv/bin/python scripts/run_all_migrations.py >/dev/null
.venv/bin/python scripts/init_db.py >/dev/null

step "App service (starts on boot, restarts on crash)"
sudo tee /etc/systemd/system/tigmy.service >/dev/null <<EOF
[Unit]
Description=Tigmy Host Shield
After=network.target

[Service]
User=${APP_USER}
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable tigmy >/dev/null 2>&1
sudo systemctl restart tigmy

step "HTTPS with Caddy (free certificate from Let's Encrypt)"
sudo tee /etc/caddy/Caddyfile >/dev/null <<EOF
${DOMAIN} {
    encode gzip
    request_body {
        max_size 15MB
    }
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "geolocation=(), microphone=()"
        -Server
    }
    reverse_proxy 127.0.0.1:8000
}
EOF
sudo systemctl reload caddy || sudo systemctl restart caddy

step "Daily backup at 03:15 (keeps 14 days in backups/)"
# (no crontab yet / nothing to filter is fine: don't let set -e/pipefail stop here)
( crontab -l 2>/dev/null | grep -v "scripts/backup.sh" || true ; echo "15 3 * * * ${APP_DIR}/scripts/backup.sh >> ${APP_DIR}/backups/backup.log 2>&1" ) | crontab -

step "Checking"
sleep 4
if curl -fsS http://127.0.0.1:8000/health >/dev/null; then echo "App: running"; else echo "App: NOT running — see: sudo journalctl -u tigmy -n 50"; fi
echo
echo "============================================"
echo "  Your site:    https://${DOMAIN}"
echo "  Admin login:  https://${DOMAIN}/admin/login"
echo "  Guest links:  https://${DOMAIN}/register/<host>  (see Admin > Hosts)"
echo "  The HTTPS certificate can take a minute the first time."
echo "  Logs: sudo journalctl -u tigmy -f    Restart: sudo systemctl restart tigmy"
echo "============================================"
