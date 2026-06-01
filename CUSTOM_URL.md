# Get a stable link: `tigmy-host-shield`

## Why not `tigmy-host-shield.trycloudflare.com`?

Free Cloudflare **quick tunnels** (`./run-public.sh`) always get a **random** name like:

`https://trigger-consumer-rise-residential.trycloudflare.com`

You **cannot** choose `tigmy-host-shield` on `trycloudflare.com`.

---

## Option 1 — Render (recommended, free tier)

Stable URL after deploy:

**https://tigmy-host-shield.onrender.com**

1. Push this project to GitHub.
2. [Render](https://render.com) → **New** → **Blueprint** → select the repo (uses `render.yaml`).
3. Set `ADMIN_PASSWORD` and any API keys in Render environment.
4. In Render env, set `BASE_URL=https://tigmy-host-shield.onrender.com`.
5. Guest link: `https://tigmy-host-shield.onrender.com/register`

(Service name in `render.yaml` is `tigmy-host-shield` — that sets the hostname.)

---

## Option 2 — Your own domain (Cloudflare Tunnel)

If you own a domain (e.g. `tigmy.ma`):

1. Add the site to [Cloudflare](https://dash.cloudflare.com).
2. Create a named tunnel and DNS record, e.g. **`tigmy-host-shield.yourdomain.com`**.
3. Set in `.env`:

```env
BASE_URL=https://tigmy-host-shield.yourdomain.com
FORCE_HTTPS=true
```

See [Cloudflare Tunnel docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/).

---

## Option 3 — Keep quick tunnel (random URL only)

```bash
./run-public.sh
```

Copy the new URL from the terminal and update `BASE_URL` in `.env` each time the URL changes.

---

## App name vs URL

- **App name** (browser title, headers): `APP_NAME=Tigmy Host Shield` in `.env`
- **Link hostname**: only changes with Render, your domain, or a new random trycloudflare URL
