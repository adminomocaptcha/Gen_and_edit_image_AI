import asyncio
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
import uuid

import httpx

from config.settings import settings



async def send_workflow_to_comfy(workflow_json: Dict[str, Any], client_id=None) -> str:
    """
    Gửi 1 workflow (dict) sang ComfyUI /prompt.
    Trả về prompt_id dùng để query /history.
    """
    payload = {
        "prompt": workflow_json,
        "client_id": client_id,
    }

    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(f"{settings.COMFYUI_URL}/prompt", json=payload)
        
        # Debug: Log response nếu bị lỗi
        if r.status_code != 200:
            print(f"[ComfyClient] ERROR: ComfyUI returned {r.status_code}")
            print(f"[ComfyClient] Response: {r.text[:500]}")
            try:
                error_data = r.json()
                if "error" in error_data:
                    print(f"[ComfyClient] Error detail: {error_data['error']}")
                if "node_errors" in error_data:
                    print(f"[ComfyClient] Node errors: {error_data['node_errors']}")
            except:
                pass
        
        r.raise_for_status()
        data = r.json()
        # ComfyUI trả về {"prompt_id": "...", "number": ..., "node_errors": {}}
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI không trả về prompt_id: {data}")
        print(f"[ComfyClient] Got prompt_id: {prompt_id}")
        return prompt_id


async def wait_for_result(prompt_id: str, poll_interval: float = 1.0) -> Dict[str, Any]:
    """
    Poll /history/{prompt_id} cho đến khi có kết quả.
    Trả về history_item: history[prompt_id]
    """
    url = f"{settings.COMFYUI_URL}/history/{prompt_id}"

    async with httpx.AsyncClient(timeout=300) as client:
        while True:
            r = await client.get(url)
            print(f"[ComfyClient] Polling {url}, status={r.status_code}")
            if r.status_code == 200:
                data = r.json()
                print(f"[ComfyClient] History keys: {list(data.keys())}")
                if prompt_id in data:
                    print(f"[ComfyClient] Found result for {prompt_id}")
                    return data[prompt_id]
            await asyncio.sleep(poll_interval)


def extract_first_image_from_history(history_item: Dict[str, Any]) -> Optional[Tuple[str, str, str]]:
    """
    Từ history[client_id], tìm ảnh đầu tiên ở outputs.
    Trả về (filename, subfolder, type) hoặc None.
    """
    outputs = history_item.get("outputs", {})
    for node_id, node_out in outputs.items():
        images = node_out.get("images")
        if not images:
            continue
        img = images[0]
        filename = img.get("filename")
        subfolder = img.get("subfolder", "")
        img_type = img.get("type", "output")
        if filename:
            return filename, subfolder, img_type
    return None


def build_image_url(filename: str, subfolder: str, img_type: str) -> str:
    """
    Tạo URL để frontend tải ảnh trực tiếp từ ComfyUI.
    """
    base = settings.COMFYUI_URL.rstrip("/")
    return f"{base}/view?filename={filename}&subfolder={subfolder}&type={img_type}"


async def copy_image_for_edit(image_url: str, comfyui_input_dir: str = None) -> str:
    """
    Download ảnh từ ComfyUI output và copy vào input folder để LoadImage có thể đọc.
    Trả về tên file đã lưu.
    """
    # Nếu không có input_dir, dùng mặc định (giả định ComfyUI ở cùng máy)
    if comfyui_input_dir is None:
        # Thử tìm ComfyUI input folder - có thể config trong settings
        comfyui_input_dir = getattr(settings, 'COMFYUI_INPUT_DIR', 'E:/ComfyUI_windows_portable_nvidia/ComfyUI/input')
    
    input_path = Path(comfyui_input_dir)
    if not input_path.exists():
        print(f"[ComfyClient] WARNING: ComfyUI input dir not found: {input_path}")
        print(f"[ComfyClient] Creating directory...")
        input_path.mkdir(parents=True, exist_ok=True)
    
    # Download ảnh từ URL
    print(f"[ComfyClient] Downloading image from: {image_url}")
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(image_url)
        r.raise_for_status()
        image_data = r.content
    
    # Tạo filename unique để tránh conflict
    import urllib.parse as up
    parsed = up.urlparse(image_url)
    qs = up.parse_qs(parsed.query)
    original_filename = qs.get("filename", [f"edit_{uuid.uuid4().hex[:8]}.png"])[0]
    filename = Path(original_filename).name
    
    # Save vào input folder
    save_path = input_path / filename
    save_path.write_bytes(image_data)
    print(f"[ComfyClient] Saved image to ComfyUI input: {save_path}")
    
    return filename
