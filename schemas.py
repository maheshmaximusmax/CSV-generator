from pydantic import BaseModel, Field

class SettingsUpdate(BaseModel):
    run_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    enabled: bool
    timezone: str = "Asia/Kolkata"
