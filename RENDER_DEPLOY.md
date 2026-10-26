# Deploy Tigmi Host Shield on Render (free)

> ⚠️ **Free Render does not keep data.** Its disk is wiped whenever the service restarts, sleeps
> (after ~15 min idle) or redeploys — guest registrations, signatures, ID scans and PDFs are lost.
> For real use, follow **[ORACLE_FREE_DEPLOY.md](ORACLE_FREE_DEPLOY.md)** instead.

**Live URL:** `https://tigmy-host-shield.onrender.com`

Guest link: `https://tigmy-host-shield.onrender.com/register`  
Admin: `https://tigmy-host-shield.onrender.com/admin/login`

---

## Step 1 — Push code to GitHub

From your project folder:

```bash
cd ~/Desktop/tigmy-host-shield
git init
git add .
git commit -m "Deploy Tigmi Host Shield to Render"
```

Create a new repo on [GitHub](https://github.com/new) (e.g. `tigmy-host-shield`), then:

```bash
git remote add origin https://github.com/YOUR_USERNAME/tigmy-host-shield.git
git branch -M main
git push -u origin main
```

---

## Step 2 — Create the app on Render

1. Go to [render.com](https://render.com) and sign up (GitHub login is easiest).
2. **New** → **Blueprint**.
3. Connect the GitHub repo you just pushed.
4. Render reads `render.yaml` and creates the web service **`tigmy-host-shield`**.
5. When asked for **`ADMIN_PASSWORD`**, choose a strong password (this is your admin login password).
6. Click **Apply** and wait for the first deploy (about 5–10 minutes).

---

## Step 3 — After deploy

| What | URL |
|------|-----|
| Guest registration | https://tigmy-host-shield.onrender.com/register |
| Admin login | https://tigmy-host-shield.onrender.com/admin/login |
| Share + QR | https://tigmy-host-shield.onrender.com/admin/share |

- **Username:** `admin` (or what you set in `ADMIN_USERNAME`)
- **Password:** the value you entered for `ADMIN_PASSWORD` in Render

In **Render → tigmy-host-shield → Environment**, you can add later:

- `GEMINI_API_KEY` + `AI_PROVIDER=gemini` for ID checks
- Change `ADMIN_USERNAME` if you want

---

## Free tier notes

- **Cold start:** If nobody visits for ~15 minutes, the next visit may take 30–60 seconds to load.
- **Data:** SQLite and uploaded files live on a temporary disk that is wiped on every restart, sleep or redeploy. Use it only for demos.
- **AI:** `render.yaml` sets `AI_PROVIDER=off` because Tesseract (needed for `local`) can't be installed on Render's Python runtime. Use Gemini with a valid `AIza…` API key if you want ID checks here.

---

## Redeploy after code changes

```bash
git add .
git commit -m "Update app"
git push
```

Render rebuilds automatically on each push to `main`.

---

## Custom domain (optional, paid name only)

Render → **Settings** → **Custom Domains** → add e.g. `register.tigmyhostshield.com`, then set:

`BASE_URL=https://register.tigmyhostshield.com`
