from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session
from datetime import datetime
import pytz

from models import Settings, JobLog
from nse_service import run_full_job

scheduler = BackgroundScheduler()
JOB_ID = "daily_nse_job"

def execute_job(db: Session, run_type: str = "scheduled"):
    try:
        result = run_full_job()
        log = JobLog(
            run_type=run_type,
            status="success",
            message=f"Sent file: {result.get('file_path')}",
            csv_url=result.get("csv_url", ""),
            created_at=datetime.utcnow()
        )
        db.add(log)
        db.commit()
        return True, "Success"
    except Exception as e:
        log = JobLog(
            run_type=run_type,
            status="failed",
            message=str(e),
            csv_url="",
            created_at=datetime.utcnow()
        )
        db.add(log)
        db.commit()
        return False, str(e)

def schedule_from_settings(db: Session):
    settings = db.query(Settings).first()
    if not settings:
        settings = Settings(run_time="09:30", enabled=True, timezone="Asia/Kolkata")
        db.add(settings)
        db.commit()
        db.refresh(settings)

    if scheduler.get_job(JOB_ID):
        scheduler.remove_job(JOB_ID)

    if settings.enabled:
        hh, mm = settings.run_time.split(":")
        tz = pytz.timezone(settings.timezone)
        trigger = CronTrigger(hour=int(hh), minute=int(mm), timezone=tz)

        # APScheduler job (db session created inside wrapper from app)
        scheduler.add_job(
            id=JOB_ID,
            func=lambda: None,  # replaced in app with safe wrapper
            trigger=trigger,
            replace_existing=True
        )

    if not scheduler.running:
        scheduler.start()
