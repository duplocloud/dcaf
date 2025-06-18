# schemas/cicd_log.py
from pydantic import BaseModel
from datetime import datetime

class CICDLogEntry(BaseModel):
    timestamp: datetime
    message: str
    stream: str
    log_group: str
    status: str  # e.g. “SUCCEEDED” or “FAILED”
    root_cause: str | None
