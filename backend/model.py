# backend/models.py
from pydantic import BaseModel
from typing import Optional, Literal, Dict, Any

Mode = Literal["NEW", "EDIT"]

Status = Literal["waiting", "processing", "done", "error"]

class GenerateRequest(BaseModel):
    user_id: str
    prompt: str
    mode: Optional[Mode] = None  # nếu None -> backend tự đoán


class GenerateResponse(BaseModel):
    job_id: str
    status: Status


class JobResult(BaseModel):
    job_id: str
    status: Literal["waiting", "processing", "done", "error"]
    image_url: Optional[str] = None
    error_message: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None
