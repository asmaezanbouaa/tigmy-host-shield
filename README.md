# Guest Registration & Signature Form

Full-stack web application for short-term rental / Airbnb guest registration. Guests complete a bilingual form, sign digitally, and the system generates a **Fiche de Police** PDF. Admins manage secure links and download submissions.

## Stack

| Layer | Technology |
|-------|------------|
| Backend | [FastAPI](https://fastapi.tiangolo.com/) (Python 3.11+) |
| Database | SQLite (default) or PostgreSQL via `DATABASE_URL` |
| ORM / migrations | SQLAlchemy 2 + Alembic |
| PDF | ReportLab (A4, 2 pages) |
| Auth | JWT in HttpOnly cookie + bcrypt |
| Frontend | Jinja2 templates, vanilla JS, responsive CSS |

## Features

- Secure random tokens for guest URLs (`/f/{token}`) — no database IDs in public links
- Link expiration and single-use mode
- Server-side validation and input sanitization
- Signature canvas (touch + mouse)
- PDF with guest data, signature, rules (FR + EN), submission ID
- Admin dashboard: login, create links, list/filter submissions, download PDFs, update status

## Production deploy (Render — recommended)

See **[RENDER_DEPLOY.md](RENDER_DEPLOY.md)** for free hosting at **`https://tigmy-host-shield.onrender.com`**.

For a VPS with your own domain, see **[DEPLOY.md](DEPLOY.md)**. Guests use a single link: `/register`.

## Quick start (local)

### Prerequisites

- Python 3.11 or newer
- `pip` and `venv`

### 1. Clone / enter project

```bash
cd airbnb_form
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` — at minimum change:

- `SECRET_KEY` — long random string (32+ characters)
- `ADMIN_PASSWORD` — not `changeme` in production
- `BASE_URL` — public URL guests use (e.g. `http://localhost:8000`)

### 3. Install and run

```bash
chmod +x run.sh
./run.sh
```

Or manually:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # if needed
python scripts/init_db.py
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000/admin/login** — default credentials from `.env` (`admin` / `changeme`).

### 4. Optional demo link

```bash
source .venv/bin/activate
python scripts/seed.py
```

Copy the printed URL and open it in a browser.

## Database setup

**Automatic (development):** `python scripts/init_db.py` creates tables and the default admin user.

**Alembic migrations:**

```bash
source .venv/bin/activate
alembic upgrade head
```

**PostgreSQL (production):**

```env
DATABASE_URL=postgresql://user:password@localhost:5432/guest_registry
```

Install driver: `pip install psycopg2-binary`

## How to create a guest link

1. Log in at `/admin/login`
2. In **Create guest form link**, enter the **property address** (shown on the PDF)
3. Optionally set a guest label and expiry days
4. Click **Create link**
5. Use **Copy** next to the guest URL in the links table

Guest URL format: `{BASE_URL}/f/{secure-token}`

## How a guest submits the form

1. Open the secure link on phone or desktop
2. Fill all required fields (bilingual labels)
3. Accept the three confirmations (read rules preview)
4. Sign in the signature box — **Submit** stays disabled until signature + checkboxes + valid fields
5. Submit — the backend validates, saves data, stores signature PNG, generates PDF
6. Success page at `/f/{token}/success`

## PDFs (admin)

Each submission generates two bilingual (FR/EN) legal-style PDFs with Morocco header styling:

- **Fiche de police** — `/admin/submissions/{id}/pdf`
- **Règlement signé** — `/admin/submissions/{id}/pdf/rules`

## Submission workflow (admin)

1. Guest submits form + **ID scan** (JPG/PNG/PDF) → status **submitted**
2. Open **Review** → view ID scan → **Mark ID verified** (file auto-deleted after 14 hours, configurable in `.env`)
3. If data is wrong: **Edit & resave** (regenerates both PDFs)
4. **Confirm** when correct, or **Archive** if invalid
5. **Archive** tab: every 90 days, **Download ZIP** of all archived records, then **Purge archive** — database clears but the **total archived count** on the tab badge is kept for history

## Guest ID retention

Set `ID_RETENTION_HOURS_AFTER_VERIFY=14` in `.env`. Guests see a clear message that the ID scan is deleted after verification.

## AI ID check (free options)

OpenAI **requires paid credits** — “exceeded quota” means no free balance on that key.

**Recommended — Google Gemini (free API):** key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)

```env
AI_PROVIDER=gemini
GEMINI_API_KEY=your-key-here
```

**100% free on your PC — Ollama:** [ollama.com](https://ollama.com) → `ollama pull moondream` → `AI_PROVIDER=ollama` in `.env`

## Project structure

```
airbnb_form/
├── app/
│   ├── main.py              # FastAPI app entry
│   ├── models.py            # DB schema
│   ├── routers/             # Guest + admin routes
│   ├── services/            # PDF, auth, storage, tokens
│   ├── templates/           # HTML (guest + admin)
│   └── static/              # CSS + JS
├── config/rules_fr.txt      # Editable internal rules (French)
├── config/rules_en.txt      # Editable internal rules (English)
├── scripts/init_db.py       # DB + admin bootstrap
├── scripts/seed.py          # Demo guest link
├── storage/signatures/      # Saved signature images
├── storage/pdfs/            # Generated PDFs
├── data/                    # SQLite database file
├── alembic/                 # Migrations
├── .env.example
└── README.md
```

## Security notes

- Tokens: `secrets.token_urlsafe(32)` — 256-bit entropy
- Public routes use **token**, not integer IDs
- Admin routes require HttpOnly session cookie
- Set `FORCE_HTTPS=true` behind TLS reverse proxy
- Change default admin password immediately
- Do not commit `.env` or `storage/` contents

## API endpoints (reference)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/f/{token}` | Guest form page |
| POST | `/api/form/{token}/submit` | Submit JSON payload |
| GET | `/admin/` | Dashboard (auth) |
| GET | `/admin/submissions/{id}/pdf` | Download PDF (auth) |

Interactive API docs (debug mode): `/api/docs`

## Production improvements (recommended)

1. **PostgreSQL** instead of SQLite for concurrency and backups
2. **Object storage** (S3, MinIO) for PDFs/signatures instead of local disk
3. **Rate limiting** on submit endpoint (e.g. slowapi)
4. **CAPTCHA** or proof-of-work on public form to reduce spam
5. **Email notifications** to host on new submission
6. **2FA** for admin accounts
7. **Audit log** for admin actions
8. **CSP headers** and stricter CORS
9. **Docker Compose** + **Caddy/nginx** for HTTPS
10. **Automated backups** of DB and storage
11. **GDPR**: data retention policy and export/delete endpoints
12. **Multi-property** admin roles

## License

MIT — use and modify freely for your rental business.
