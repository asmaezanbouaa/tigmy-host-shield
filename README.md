# Tigmy Host Shield

Guest registration platform for short-term rental hosts (Airbnb-style). Guests complete a secure form in **French, English, or Arabic**, upload an ID scan, sign digitally, and receive official PDFs. Hosts review submissions in an admin dashboard.

**Production URL (Render):** [https://tigmy-host-shield.onrender.com](https://tigmy-host-shield.onrender.com)

| Page | Path |
|------|------|
| Guest registration | `/register` |
| Admin login | `/admin/login` |
| Share link & QR | `/admin/share` |

---

## What it does

- **One guest link** for all bookings — no apartment picker on the form
- **Fiche de police** + **signed rules** (FR/EN) as PDFs with Morocco-style headers
- Property on PDFs shows **`waiting for dynamic assigning`** until booking sync is added
- **ID scans** removed automatically after host verification (configurable retention)
- Admin: review, confirm, edit, archive, calendar, CSV export, optional AI ID check

---

## Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI (Python 3.11+) |
| Database | SQLite (default) |
| PDF | ReportLab + Pillow |
| Frontend | Jinja2, vanilla JS |
| Auth | JWT cookie + bcrypt |

---

## Quick start (local)

```bash
cd tigmy-host-shield
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: SECRET_KEY, ADMIN_PASSWORD, BASE_URL=http://localhost:8000
chmod +x run.sh
./run.sh
```

- **Guest:** http://localhost:8000/register  
- **Admin:** http://localhost:8000/admin/login  

---

## Deploy on Render (free)

Stable hostname: **`https://tigmy-host-shield.onrender.com`**

Full steps: **[RENDER_DEPLOY.md](RENDER_DEPLOY.md)**

1. Push this repo to GitHub  
2. [Render](https://render.com) → **New** → **Blueprint**  
3. Set **`ADMIN_PASSWORD`** when prompted  
4. Share `/register` with guests  

---

## Environment variables

See **[.env.example](.env.example)**. Important keys:

| Variable | Purpose |
|----------|---------|
| `BASE_URL` | Public URL (guest links & QR) |
| `SECRET_KEY` | Session signing (long random string) |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Admin login |
| `AI_PROVIDER` | `off`, `local`, `gemini`, or `openai` |

---

## Project layout

```
tigmy-host-shield/
├── app/                 # FastAPI app, templates, static assets
├── config/
│   ├── morocco_coat_of_arms.png   # PDF header source (committed)
│   ├── morocco_coat_header.png  # generated at runtime (gitignored)
│   └── rules_fr.txt / rules_en.txt / rules_ar.txt
├── data/                # SQLite DB (gitignored)
├── storage/             # Signatures, PDFs, ID uploads (gitignored)
├── scripts/             # init_db, migrations, Render build
├── render.yaml          # Render Blueprint
└── run.sh               # Local dev server
```

---

## PDF assets & git

Only **`config/morocco_coat_of_arms.png`** is stored in git. On startup the app builds **`config/morocco_coat_header.png`** for the green PDF band.

Everything under **`storage/`** (guest signatures, ID scans, generated PDFs) and **`data/`** is **gitignored** — never commit guest personal data.

Regenerate all submission PDFs after asset changes:

```bash
source .venv/bin/activate
python scripts/regenerate_pdfs.py
```

---

## Other docs

- **[RENDER_DEPLOY.md](RENDER_DEPLOY.md)** — Render hosting  
- **[DEPLOY.md](DEPLOY.md)** — VPS + custom domain  
- **[CUSTOM_URL.md](CUSTOM_URL.md)** — URL options explained  

---

## License

Private / host use — adjust as needed for your deployment.
