# NSE CSV Telegram Dashboard

A free, always-on system that downloads the NSE live-market-indices CSV at a scheduled time and sends it to your Telegram channel.  
Control everything from a web dashboard — no local machine or coding needed after setup.

---

## Architecture

```
GitHub Pages (docs/)          Render free tier (backend/)
┌─────────────────┐           ┌──────────────────────────┐
│  HTML/CSS/JS    │  ──API──▶ │  FastAPI + APScheduler   │
│  Dashboard UI   │           │  SQLite logs              │
└─────────────────┘           │  NSE download + Telegram  │
                               └──────────────────────────┘
```

| Part | Where | Cost |
|------|-------|------|
| Frontend dashboard | GitHub Pages (`/docs`) | Free |
| Backend API + scheduler | Render Web Service (`/backend`) | Free |
| GitHub Actions (optional backup) | `.github/workflows/` | Free |

---

## One-time Setup (step by step)

### Step 1 — Push this repo to GitHub

Make sure all files are committed and pushed to `main`.

### Step 2 — Enable GitHub Pages

1. Go to your repo → **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: `main` / Folder: `/docs`
4. Click **Save**
5. Note your Pages URL: `https://<your-username>.github.io/CSV-generator`

### Step 3 — Deploy backend to Render (free)

1. Go to [https://render.com](https://render.com) and sign up (free)
2. Click **New → Web Service**
3. Connect your GitHub repo (`CSV-generator`)
4. Render will auto-detect `render.yaml` — click **Apply**
5. Add environment variables (**Environment** tab):

| Variable | Value |
|----------|-------|
| `TELEGRAM_BOT_TOKEN` | Your bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Your channel/group chat ID |
| `API_KEY` | Any strong random string (e.g. `openssl rand -hex 32`) |
| `APP_TIMEZONE` | `Asia/Kolkata` (default) |

6. Click **Deploy** — wait ~2 min for first build
7. Note your Render URL: `https://nse-csv-dashboard.onrender.com` (or similar)

> **Note:** On Render's free tier the service sleeps after 15 min of inactivity.  
> The scheduled job runs inside the process so it stays active while the process is alive.  
> Use [UptimeRobot](https://uptimerobot.com) (free) to ping `/health` every 5 min to prevent sleeping.

### Step 4 — Connect the dashboard

1. Open your GitHub Pages URL
2. A **Setup** dialog appears — enter:
   - **Backend URL**: your Render URL (e.g. `https://nse-csv-dashboard.onrender.com`)
   - **API Key**: the `API_KEY` value you set in Render
3. Click **Save & Connect**
4. The dashboard loads — set your schedule time and click **Save Settings**

---

## How to use

| Action | How |
|--------|-----|
| Change schedule time | Set time in dashboard → Save Settings |
| Trigger immediately | Click **Run Now** button |
| View job history | Recent Job Logs section |
| Change backend URL or API key | Click ⚙️ Config button |

---

## Project structure

```
CSV-generator/
├── backend/                 ← Python FastAPI backend (deploy to Render)
│   ├── main.py              ← FastAPI app (JSON API + APScheduler)
│   ├── database.py          ← SQLite setup
│   ├── models.py            ← SQLAlchemy models
│   ├── nse_service.py       ← NSE download + Telegram send (with retry)
│   └── requirements.txt     ← Python dependencies
│
├── docs/                    ← GitHub Pages frontend
│   ├── index.html           ← Dashboard HTML
│   ├── script.js            ← Dashboard JS (calls backend API)
│   └── style.css            ← Styles
│
├── .github/workflows/
│   └── nse_telegram.yml     ← Optional: GitHub Actions fallback job
│
├── render.yaml              ← Render deployment config
├── .env.example             ← Example environment variables
└── nse_to_telegram.py       ← Standalone script (used by Actions)
```

---

## Backend API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (no auth required) |
| GET | `/api/settings` | Get current schedule settings |
| POST | `/api/settings` | Update schedule settings |
| POST | `/api/run-now` | Trigger immediate CSV download + send |
| GET | `/api/logs` | Get recent job logs |

All endpoints except `/health` require `X-API-Key` header when `API_KEY` env var is set.

---

## Telegram bot setup (if not done)

1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Copy the token
3. Add the bot as **Admin** to your channel/group
4. Get chat ID: message [@userinfobot](https://t.me/userinfobot) in your channel, or use `https://api.telegram.org/bot<TOKEN>/getUpdates`
