# Put Tigmi Host Shield online — free, secure, with your own link

Result: **`https://YOURNAME.duckdns.org`** running 24/7 on a free Oracle Cloud server, with HTTPS,
a firewall, automatic security updates, protection against password guessing, and daily backups.
Your computer does not need to stay on.

Cost: **0**. Oracle asks for a card to check your identity; Always Free resources are never charged.
(Optional later: a real domain such as `tigmi.ma` / `tigmi.com` costs about 10 € a year.)

---

## 1. Create the free server (Oracle Cloud) — about 15 minutes

1. Sign up at <https://signup.cloud.oracle.com>. Choose a home region near Morocco
   (*Spain Central (Madrid)* or *France South (Marseille)*). It cannot be changed later.
2. Menu → **Compute → Instances → Create instance**:
   - **Image:** Canonical **Ubuntu 24.04**
   - **Shape:** *Ampere* `VM.Standard.A1.Flex`, 1 OCPU, 6 GB memory (Always Free).
     If it says "out of capacity", choose *AMD* `VM.Standard.E2.1.Micro` (also free).
   - **SSH keys:** *Generate a key pair for me* → **Save private key** (e.g. `oracle.key`).
3. Click **Create**. When it shows *Running*, copy the **Public IP address**.
4. Open the web ports: on the instance page click the **Subnet** → **Default Security List** →
   **Add Ingress Rules**, twice:

   | Source CIDR | IP protocol | Destination port range |
   |---|---|---|
   | `0.0.0.0/0` | TCP | `80` |
   | `0.0.0.0/0` | TCP | `443` |

## 2. Get your free link (DuckDNS) — 2 minutes

1. Go to <https://www.duckdns.org> and sign in (Google or GitHub).
2. Type the name you want (e.g. `tigmi`) → **add domain**.
3. Paste the server's **public IP** in *current ip* → **update ip**.

Your link is now `tigmi.duckdns.org`.

## 3. Install everything with one command

From your computer, copy your current data to the server and connect
(replace `YOUR_IP` and the key path):

```bash
cd ~/Desktop/tigmy-host-shield && ./scripts/backup.sh
scp -i ~/Downloads/oracle.key "$(ls -t backups/tigmy-backup-*.tar.gz | head -1)" ubuntu@YOUR_IP:~/tigmy-data.tar.gz
ssh -i ~/Downloads/oracle.key ubuntu@YOUR_IP
```

(If `ssh` complains about permissions on the key: `chmod 600 ~/Downloads/oracle.key`.)

Then, **on the server**:

```bash
git clone https://github.com/asmaezanbouaa/tigmy-host-shield.git
cd tigmy-host-shield
DOMAIN=tigmi.duckdns.org IMPORT=~/tigmy-data.tar.gz ./scripts/server-setup.sh
```

It asks for an **admin username and password** (12+ characters, different from the username),
then sets up: packages, firewall, security updates, fail2ban, the app as a service, HTTPS with a
free Let's Encrypt certificate, security headers and a daily backup at 03:15.

Open `https://tigmi.duckdns.org/admin/login` — done. Each host's guest link is
`https://tigmi.duckdns.org/register/<host>` (see **Admin → Hosts**).

> Without `IMPORT=…` you start with an empty site and create your hosts from the admin panel.

## After going live

- **Change weak passwords**: host users' passwords in **Admin → Host users → New password**.
- **Update the app** after changes are pushed to GitHub:
  ```bash
  cd ~/tigmy-host-shield && git pull && ./scripts/server-setup.sh
  ```
  (your data and settings are kept).
- **Logs:** `sudo journalctl -u tigmy -f` · **Restart:** `sudo systemctl restart tigmy`
- **Backups** are in `~/tigmy-host-shield/backups/` (14 days). Copy one to your computer now and then:
  ```bash
  scp -i ~/Downloads/oracle.key "ubuntu@YOUR_IP:tigmy-host-shield/backups/tigmy-backup-*.tar.gz" ~/
  ```
- **If the server's IP ever changes**, update it on duckdns.org.

## Using a real domain later (optional)

Buy the domain, add a DNS **A record** pointing to the server's IP, then on the server:

```bash
cd ~/tigmy-host-shield && DOMAIN=www.yourdomain.com ./scripts/server-setup.sh
```
