# backend/app.py

import json
import redis.asyncio as redis
from fastapi import FastAPI, HTTPException

from config.settings import settings
from .model import GenerateRequest, GenerateResponse, JobResult
from .utils import gen_job_id, OllamaModeClassifier
from typing import Optional

QUEUE_KEY = "image_jobs"
JOB_KEY_PREFIX = "job:"
LAST_IMAGE_PREFIX = "last_image:"

app = FastAPI(title="Qwen Image Service")

# Tạo 1 instance classifier dùng chung
classifier = OllamaModeClassifier(
    host=settings.OLLAMA_HOST,  
    model=settings.OLLAMA_MODEL,                  
)

async def get_redis_client() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt không được để trống")

    rds = await get_redis_client()

    if req.mode is not None:
        mode = req.mode
    else:
        # Check user đã có ảnh trước đó chưa
        last_img = await rds.get(f"{LAST_IMAGE_PREFIX}{req.user_id}")

        if not last_img:
            mode = "NEW"
        else:
            mode = await classifier.classify_mode(req.prompt)
            if mode is None:
                mode = OllamaModeClassifier._fallback_rule(req.prompt)

    # 3) Tạo job_id
    job_id = gen_job_id()

    job_data = {
        "job_id": job_id,
        "user_id": req.user_id,
        "prompt": req.prompt,
        "mode": mode,
    }

    # 4) Lưu trạng thái job ban đầu 
    await rds.set(
        f"{JOB_KEY_PREFIX}{job_id}",
        json.dumps({
            "status": "waiting",
            "image_url": None,
            "error_message": None,
        }),
    )

    # 5) Đẩy job vào queue cho worker xử lý
    await rds.lpush(QUEUE_KEY, json.dumps(job_data))

    return GenerateResponse(job_id=job_id, status="waiting")


@app.get("/result/{job_id}", response_model=JobResult)
async def get_result(job_id: str):
    """
    Trả về trạng thái job + image_url (nếu xong).
    """
    rds = await get_redis_client()
    data = await rds.get(f"{JOB_KEY_PREFIX}{job_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Job không tồn tại")

    obj = json.loads(data)
    status = obj.get("status", "waiting")
    image_url: Optional[str] = obj.get("image_url")
    error_message: Optional[str] = obj.get("error_message")

    return JobResult(
        job_id=job_id,
        status=status,
        image_url=image_url,
        error_message=error_message,
        extra=None,
    )
