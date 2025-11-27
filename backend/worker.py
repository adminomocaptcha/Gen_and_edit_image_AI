# backend/worker.py

import asyncio
import json
from typing import Any, Dict

import redis.asyncio as redis

from config.settings import settings

from .workflow_builder import build_gen_workflow, build_edit_workflow
from .comfy_client import (
    send_workflow_to_comfy,
    wait_for_result,
    extract_first_image_from_history,
    build_image_url,
    copy_image_for_edit,
)


QUEUE_KEY = "image_jobs"  # danh sách job
JOB_KEY_PREFIX = "job:"   # job:{job_id}
LAST_IMAGE_PREFIX = "last_image:"  # last_image:{user_id}


async def get_redis_client() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


async def process_job(rds: redis.Redis, job_data: Dict[str, Any]) -> None:
    job_id = job_data["job_id"]
    user_id = job_data["user_id"]
    mode = job_data["mode"]          
    prompt = job_data["prompt"]

    print(f"[Worker] Processing job {job_id}, mode={mode}, prompt={prompt[:50]}...")

    # Cập nhật trạng thái job -> processing
    await rds.set(
        f"{JOB_KEY_PREFIX}{job_id}",
        json.dumps({"status": "processing", "image_url": None, "error_message": None}),
    )

    try:
        if mode == "NEW":
            workflow = build_gen_workflow(prompt, job_id)
        else:
            last_img = await rds.get(f"{LAST_IMAGE_PREFIX}{user_id}")
            if not last_img:
                # nếu chưa có ảnh, fallback sang GEN
                workflow = build_gen_workflow(prompt, job_id)
            else:
                # Copy ảnh từ output sang input folder trước
                print(f"[Worker] Preparing image for edit: {last_img}")
                try:
                    # Download và save vào input folder
                    filename = await copy_image_for_edit(last_img)
                    print(f"[Worker] Image ready in input folder: {filename}")
                    # Dùng filename trong input folder
                    workflow = build_edit_workflow(prompt, filename, job_id)
                except Exception as e:
                    print(f"[Worker] ERROR: Failed to prepare image for edit: {e}")
                    import traceback
                    traceback.print_exc()
                    raise RuntimeError(f"Cannot prepare image for edit: {e}")

        client_id = job_id 

        print(f"[Worker] Sending workflow to ComfyUI, client_id={client_id}")
        print(f"[Worker] Workflow has {len(workflow)} nodes")
        
        # Debug: Lưu workflow để kiểm tra
        from .workflow_builder import save_debug_workflow
        save_debug_workflow(workflow, f"debug_{mode}_{job_id[:8]}.json")
        print(f"[Worker] Saved debug workflow to workflows/_debug/")
        
        prompt_id = await send_workflow_to_comfy(workflow, client_id=client_id)

        # Đợi kết quả
        print(f"[Worker] Waiting for ComfyUI result, prompt_id={prompt_id}...")
        history_item = await wait_for_result(prompt_id)
        print(f"[Worker] Got history item: {list(history_item.keys())}")
        img_info = extract_first_image_from_history(history_item)
        if not img_info:
            raise RuntimeError("Không tìm thấy ảnh output trong history ComfyUI")

        filename, subfolder, img_type = img_info
        image_url = build_image_url(filename, subfolder, img_type)
        print(f"[Worker] Image URL: {image_url}")

        # Lưu ảnh gần nhất cho user (phục vụ EDIT sau này)
        await rds.set(f"{LAST_IMAGE_PREFIX}{user_id}", image_url)

        # Cập nhật trạng thái job -> done
        await rds.set(
            f"{JOB_KEY_PREFIX}{job_id}",
            json.dumps(
                {
                    "status": "done",
                    "image_url": image_url,
                    "error_message": None,
                }
            ),
        )
        print(f"[Worker] Job {job_id} completed successfully")

    except Exception as e:
        # Nếu lỗi thì lưu trạng thái error
        print(f"[Worker] ERROR processing job {job_id}: {e}")
        import traceback
        traceback.print_exc()
        await rds.set(
            f"{JOB_KEY_PREFIX}{job_id}",
            json.dumps(
                {
                    "status": "error",
                    "image_url": None,
                    "error_message": str(e),
                }
            ),
        )


async def worker_loop(worker_id: int) -> None:
    rds = await get_redis_client()
    print(f"[Worker {worker_id}] Started")

    while True:
        # BRPOP block đến khi có job mới
        _, job_json = await rds.brpop(QUEUE_KEY)
        try:
            job_data = json.loads(job_json)
        except Exception:
            print(f"[Worker {worker_id}] Invalid job JSON: {job_json}")
            continue

        print(f"[Worker {worker_id}] Processing job {job_data.get('job_id')}")
        await process_job(rds, job_data)


async def main(num_workers: int = 1) -> None:
    tasks = [asyncio.create_task(worker_loop(i)) for i in range(num_workers)]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    # Tăng số workers dựa trên khả năng xử lý của ComfyUI
    # Mỗi worker = 1 job đồng thời
    asyncio.run(main(num_workers=4))  # 4 jobs cùng lúc
