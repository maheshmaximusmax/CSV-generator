import os
import secrets
from datetime import datetime

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import Base, SessionLocal, engine
from models import JobLog, Settings
from nse_service import run_full_job, send_failure_alert

# --- DB init ---
Base.metadata.create_all(bind=engine)

# --- Scheduler ---
scheduler = BackgroundScheduler()
JOB_ID = "daily_nse_job"

# --- App ---
app = FastAPI(title="NSE CSV Dashboard API")

# CORS: allow GitHub Pages and any other origin (API-key protected endpoints)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# --- Dependency: DB session ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Dependency: API key auth ---
def verify_api_key(request: Request):
    api_key = os.getenv("API_KEY", "").strip()
    if not api_key:
        # No API key configured — open access (not recommended for production)
        return True
    provided = request.headers.get("X-API-Key", "")
    if not secrets.compare_digest(provided, api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return True


# --- Helpers ---
def get_or_create_settings(db: Session) -> Settings:
    settings = db.query(Settings).first()
    if not settings:
        settings = Settings(
            run_time="09:30",
            enabled=True,
            timezone=os.getenv("APP_TIMEZONE", "Asia/Kolkata"),
            updated_at=datetime.utcnow(),
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def scheduled_wrapper():
    db = SessionLocal()
    try:
        result = run_full_job()
        log = JobLog(
            run_type="scheduled",
            status="success",
            message=f"Sent file: {result.get('file_path')}",
            csv_url=result.get("csv_url", ""),
            created_at=datetime.utcnow(),
        )
        db.add(log)
        db.commit()
    except Exception as e:
        err_msg = str(e)
        log = JobLog(
            run_type="scheduled",
            status="failed",
            message=err_msg,
            csv_url="",
            created_at=datetime.utcnow(),
        )
        db.add(log)
        db.commit()
        send_failure_alert(err_msg)
    finally:
        db.close()


def reschedule_job(db: Session):
    settings = get_or_create_settings(db)

    if scheduler.get_job(JOB_ID):
        scheduler.remove_job(JOB_ID)

    if settings.enabled:
        hh, mm = settings.run_time.split(":")
        tz = pytz.timezone(settings.timezone)
        trigger = CronTrigger(hour=int(hh), minute=int(mm), timezone=tz)
        scheduler.add_job(
            id=JOB_ID,
            func=scheduled_wrapper,
            trigger=trigger,
            replace_existing=True,
        )

    if not scheduler.running:
        scheduler.start()


# --- Startup ---
@app.on_event("startup")
def startup():
    db = SessionLocal()
    try:
        get_or_create_settings(db)
        reschedule_job(db)
    finally:
        db.close()


@app.on_event("shutdown")
def shutdown():
    if scheduler.running:
        scheduler.shutdown(wait=False)


# --- Routes ---

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


class SettingsUpdate(BaseModel):
    run_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    enabled: bool = True
    timezone: str = "Asia/Kolkata"


@app.get("/api/settings")
def get_settings(
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key),
):
    settings = get_or_create_settings(db)
    next_run = None
    job = scheduler.get_job(JOB_ID)
    if job and settings.enabled:
        next_run = job.next_run_time.isoformat() if job.next_run_time else None

    return {
        "run_time": settings.run_time,
        "enabled": settings.enabled,
        "timezone": settings.timezone,
        "updated_at": settings.updated_at.isoformat() if settings.updated_at else None,
        "next_run": next_run,
    }


@app.post("/api/settings")
def update_settings(
    body: SettingsUpdate,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key),
):
    try:
        hh, mm = body.run_time.split(":")
        if not (0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
            raise ValueError()
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid time format. Use HH:MM (e.g. 09:30)")

    try:
        pytz.timezone(body.timezone)
    except pytz.exceptions.UnknownTimeZoneError:
        raise HTTPException(status_code=400, detail=f"Unknown timezone: {body.timezone}")

    settings = get_or_create_settings(db)
    settings.run_time = body.run_time
    settings.enabled = body.enabled
    settings.timezone = body.timezone
    settings.updated_at = datetime.utcnow()
    db.add(settings)
    db.commit()

    reschedule_job(db)

    next_run = None
    job = scheduler.get_job(JOB_ID)
    if job and settings.enabled:
        next_run = job.next_run_time.isoformat() if job.next_run_time else None

    return {
        "run_time": settings.run_time,
        "enabled": settings.enabled,
        "timezone": settings.timezone,
        "next_run": next_run,
        "message": "Settings saved and scheduler updated.",
    }


@app.post("/api/run-now")
def run_now(
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key),
):
    try:
        result = run_full_job()
        log = JobLog(
            run_type="manual",
            status="success",
            message=f"Sent file: {result.get('file_path')}",
            csv_url=result.get("csv_url", ""),
            created_at=datetime.utcnow(),
        )
        db.add(log)
        db.commit()
        return {"status": "success", "message": "CSV downloaded and sent to Telegram."}
    except Exception as e:
        err_msg = str(e)
        log = JobLog(
            run_type="manual",
            status="failed",
            message=err_msg,
            csv_url="",
            created_at=datetime.utcnow(),
        )
        db.add(log)
        db.commit()
        raise HTTPException(status_code=500, detail=err_msg)


@app.get("/api/logs")
def get_logs(
    limit: int = 20,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key),
):
    logs = (
        db.query(JobLog)
        .order_by(JobLog.created_at.desc())
        .limit(min(limit, 100))
        .all()
    )
    return [
        {
            "id": log.id,
            "run_type": log.run_type,
            "status": log.status,
            "message": log.message,
            "csv_url": log.csv_url,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]
