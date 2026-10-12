# Deploy for free on Oracle Cloud (data is kept)

Oracle Cloud "Always Free" gives you a small Linux server that never expires and keeps its disk,
so the database, signatures, ID scans and PDFs survive restarts (unlike free Render).
You get a free address like **`https://tigmy-host-shield.duckdns.org`** with HTTPS.

Time: about 1–2 hours. Oracle asks for a card to verify your identity; Always Free resources are not charged.

---

## 1. Create the server

1. Sign up at <https://signup.cloud.oracle.com>. Pick a **home region** close to Morocco
   (e.g. *Spain Central (Madrid)* or *France South (Marseille)*). It cannot be changed later.
2. Menu → **Compute → Instances → Create instance**.
3. **Image:** Canonical **Ubuntu 24.04**.
4. **Shape:** *Ampere* `VM.Standard.A1.Flex` with 1 OCPU / 6 GB (Always Free).
   If it says "out of capacity", use *AMD* `VM.Standard.E2.1.Micro` instead (also free, 1 GB is enough).
5. **SSH keys:** choose *Generate a key pair* and **download the private key** (e.g. `oracle.key`).
6. Click **Create**. When it's running, copy the **Public IP address**.

## 2. Open ports 80 and 443

In Oracle: on the instance page, click the **subnet** → **Default Security List** → **Add Ingress Rules**:

| Source CIDR | IP protocol | Destination port |
|---|---|---|
| `0.0.0.0/0` | TCP | `80` |
| `0.0.0.0/0` | TCP | `443` |

## 3. Get a free address (DuckDNS)

1. Go to <https://www.duckdns.org> and sign in.
2. Create the subdomain `tigmy-host-shield` (or any free name).
3. Put the server's **public IP** in the *current ip* box → **update ip**.

Your address is now `tigmy-host-shield.duckdns.org`.

## 4. Connect to the server

On your computer:

```bash
chmod 600 ~/Downloads/oracle.key
ssh -i ~/Downloads/oracle.key ubuntu@YOUR_PUBLIC_IP
```

Everything below runs **on the server**.

## 5. Install system packages

```bash
sudo apt update && sudo apt install -y python3 python3-venv git caddy \
  tesseract-ocr tesseract-ocr-eng tesseract-ocr-fra

# Oracle's Ubuntu image blocks web ports in its own firewall — open them
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

On the 1 GB AMD server, add swap so installs don't run out of memory:

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 6. Get the code

```bash
cd ~
git clone https://github.com/asmaezanbouaa/tigmy-host-shield.git
cd tigmy-host-shield
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

(If the GitHub repo is private, Git asks for your username and a
[personal access token](https://github.com/settings/tokens) as the password.)

## 7. Production settings

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # copy the output
nano .env
```

Change these lines (the app **refuses to start** in production if they are unsafe):

```env
APP_ENV=production
DEBUG=false
SECRET_KEY=<paste the random string>
BASE_URL=https://tigmy-host-shield.duckdns.org
FORCE_HTTPS=true
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<strong password, 10+ characters>
AI_PROVIDER=local
```

Save with `Ctrl+O`, `Enter`, exit with `Ctrl+X`. Then prepare the database:

```bash
.venv/bin/python scripts/run_all_migrations.py
.venv/bin/python scripts/init_db.py
```

## 8. Run it as a service (starts on boot, restarts on crash)

```bash
sudo tee /etc/systemd/system/tigmy.service > /dev/null << 'EOF'
[Unit]
Description=Tigmy Host Shield
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/tigmy-host-shield
ExecStart=/home/ubuntu/tigmy-host-shield/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now tigmy
sudo systemctl status tigmy --no-pager
```

Keep `--workers 1`: SQLite and the login/submission limits are designed for one process.

## 9. HTTPS with Caddy

```bash
sudo tee /etc/caddy/Caddyfile > /dev/null << 'EOF'
tigmy-host-shield.duckdns.org {
    reverse_proxy 127.0.0.1:8000
    encode gzip
    request_body {
        max_size 15MB
    }
}
EOF
sudo systemctl reload caddy
```

Caddy gets a free Let's Encrypt certificate automatically (give it a minute).

## 10. Daily backups

```bash
chmod +x scripts/backup.sh
./scripts/backup.sh          # test once
(crontab -l 2>/dev/null; echo "15 3 * * * /home/ubuntu/tigmy-host-shield/scripts/backup.sh >> /home/ubuntu/tigmy-host-shield/backups/backup.log 2>&1") | crontab -
```

This keeps the last 14 daily backups in `backups/`. To also keep a copy on your own computer,
run this from your computer from time to time:

```bash
scp -i ~/Downloads/oracle.key "ubuntu@YOUR_PUBLIC_IP:tigmy-host-shield/backups/tigmy-backup-*.tar.gz" ~/tigmy-backups/
```

## 11. Check it works

- Guest form: `https://tigmy-host-shield.duckdns.org/register`
- Admin: `https://tigmy-host-shield.duckdns.org/admin/login`
- Admin → Share: copy the link / print the QR code for your apartments

Do one full test registration with your own ID before sharing the link.

---

## Updating the app later

```bash
cd ~/tigmy-host-shield
git pull
.venv/bin/pip install -r requirements.txt
sudo systemctl restart tigmy
```

## If something goes wrong

```bash
sudo journalctl -u tigmy -n 50 --no-pager    # app errors (including unsafe-settings messages)
sudo journalctl -u caddy -n 50 --no-pager    # HTTPS / certificate errors
```
