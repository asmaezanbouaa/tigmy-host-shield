# Deploy guest registration online

This app is a **FastAPI** service with SQLite, file storage (`data/`, `storage/`), and an admin dashboard. Guests use **one link**: `https://your-domain.com/register`.

## Before you deploy

1. **Production `.env`** (copy from `.env.example`):

```env
APP_ENV=production
DEBUG=false
SECRET_KEY=<64+ random characters>
BASE_URL=https://your-domain.com
FORCE_HTTPS=true

ADMIN_USERNAME=admin
ADMIN_PASSWORD=<strong password>

HOST=127.0.0.1
PORT=8000
```

4. **Do not commit** `.env` or `storage/` / `data/` with real guest data.

## Quick deploy on a VPS (Ubuntu + Caddy)

### 1. Server setup

```bash
sudo apt update && sudo apt install -y python3 python3-venv git caddy
```

Upload or clone the project to e.g. `/opt/guest-registry`, then:

```bash
cd /opt/guest-registry
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: BASE_URL, SECRET_KEY, ADMIN_PASSWORD, DEBUG=false
chmod +x run.prod.sh
./run.prod.sh   # test once; Ctrl+C after it starts
```

### 2. Systemd service

```bash
sudo tee /etc/systemd/system/guest-registry.service << 'EOF'
[Unit]
Description=Guest registration form
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/guest-registry
Environment=PATH=/opt/guest-registry/.venv/bin
ExecStart=/opt/guest-registry/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo chown -R www-data:www-data /opt/guest-registry/data /opt/guest-registry/storage
sudo systemctl daemon-reload
sudo systemctl enable --now guest-registry
```

### 3. Caddy (HTTPS)

Point DNS `your-domain.com` → server IP, then:

```bash
sudo tee /etc/caddy/Caddyfile << 'EOF'
your-domain.com {
    reverse_proxy 127.0.0.1:8000
    encode gzip
}
EOF

sudo systemctl reload caddy
```

Caddy obtains a Let’s Encrypt certificate automatically.

### 4. Verify

- Guest form: `https://your-domain.com/register`
- Admin: `https://your-domain.com/admin/login`
- Admin → Share: copy link / QR (uses `BASE_URL`)

## Persistence

Back up regularly:

- `data/guest_registry.db`
- `storage/` (signatures, ID scans, PDFs, archive ZIPs)

## AI on the server (optional)

- **Local OCR**: `sudo apt install tesseract-ocr tesseract-ocr-fra`, `AI_PROVIDER=local` (unlimited, no daily quota)

## Updates

```bash
cd /opt/guest-registry
git pull   # or upload new files
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart guest-registry
```

## Nginx alternative

Use `proxy_pass http://127.0.0.1:8000` and certbot for TLS. Set `BASE_URL` and `FORCE_HTTPS=true` the same way.
