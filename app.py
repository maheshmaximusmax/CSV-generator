import os
from datetime import datetime
from fastapi import FastAPI, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session
import secrets

from database import SessionLocal, engine, Base
from models import Settings, JobLog
from scheduler_service import scheduler, JOB_ID
from apscheduler.triggers.cron import CronTrigger
import pytz
from nse_service import run_full_job

Base.metadata.create_all(bind=engine)

app = FastAPI(title="NSE CSV Dashboard")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
security = HTTPBasic()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def check_auth(credentials: HTTPBasicCredentials = Depends(security)):
    user = os.getenv("DASHBOARD_USERNAME", "admin")
    pwd = os.getenv("DASHBOARD_PASSWORD", "admin123")

    correct_user = secrets.compare_digest(credentials.username, user)
    correct_pwd = secrets.compare_digest(credentials.password, pwd)
    if not (correct_user and correct_pwd):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return credentials.username

def get_or_create_settings(db: Session):
    settings = db.query(Settings).first()
    if not settings:
        settings = Settings(
            run_time="09:30",
            enabled=True,
            timezone=os.getenv("APP_TIMEZONE", "Asia/Kolkata"),
            updated_at=datetime.utcnow()
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings

def scheduled_wrapper():
    db = SessionLocal()
    try:
        try:
            result = run_full_job()
            log = JobLog(
                run_type="scheduled",
                status="success",
                message=f"Sent file: {result.get('file_path')}",
                csv_url=result.get("csv_url", ""),
                created_at=datetime.utcnow()
            )
            db.add(log)
            db.commit()
        except Exception as e:
            log = JobLog(
                run_type="scheduled",
                status="failed",
                message=str(e),
                csv_url="",
                created_at=datetime.utcnow()
            )
            db.add(log)
            db.commit()
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
            replace_existing=True
        )

    if not scheduler.running:
        scheduler.start()

@app.on_event("startup")
def startup():
    db = SessionLocal()
    try:
        get_or_create_settings(db)
        reschedule_job(db)
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: str = Depends(check_auth)
):
    settings = get_or_create_settings(db)
    logs = db.query(JobLog).order_by(JobLog.created_at.desc()).limit(20).all()
    next_run = None
    job = scheduler.get_job(JOB_ID)
    if job and settings.enabled:
        next_run = str(job.next_run_time)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "settings": settings,
        "logs": logs,
        "next_run": next_run,
        "user": user
    })

@app.post("/save")
def save_settings(
    run_time: str = Form(...),
    enabled: str = Form("off"),
    timezone: str = Form("Asia/Kolkata"),
    db: Session = Depends(get_db),
    user: str = Depends(check_auth)
):
    # Basic validation HH:MM
    try:
        hh, mm = run_time.split(":")
        hh = int(hh); mm = int(mm)
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid time format. Use HH:MM")

    settings = get_or_create_settings(db)
    settings.run_time = run_time
    settings.enabled = enabled == "on"
    settings.timezone = timezone
    settings.updated_at = datetime.utcnow()

    db.add(settings)
    db.commit()

    reschedule_job(db)
    return RedirectResponse(url="/", status_code=303)

@app.post("/run-now")
def run_now(
    db: Session = Depends(get_db),
    user: str = Depends(check_auth)
):
    try:
        result = run_full_job()
        log = JobLog(
            run_type="manual",
            status="success",
            message=f"Sent file: {result.get('file_path')}",
            csv_url=result.get("csv_url", ""),
            created_at=datetime.utcnow()
        )
        db.add(log)
        db.commit()
    except Exception as e:
        log = JobLog(
            run_type="manual",
            status="failed",
            message=str(e),
            csv_url="",
            created_at=datetime.utcnow()
        )
        db.add(log)
        db.commit()

    return RedirectResponse(url="/", status_code=303)
