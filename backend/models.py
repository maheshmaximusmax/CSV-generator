from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from datetime import datetime
from database import Base


class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    run_time = Column(String(5), default="09:30")  # HH:MM
    enabled = Column(Boolean, default=True)
    timezone = Column(String(64), default="Asia/Kolkata")
    updated_at = Column(DateTime, default=datetime.utcnow)


class JobLog(Base):
    __tablename__ = "job_logs"

    id = Column(Integer, primary_key=True, index=True)
    run_type = Column(String(20), default="scheduled")  # scheduled/manual
    status = Column(String(20), default="success")      # success/failed
    message = Column(Text, default="")
    csv_url = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
