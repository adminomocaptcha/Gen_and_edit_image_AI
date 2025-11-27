# backend/workflow_builder.py

import json
import random
from pathlib import Path
from typing import Dict, Any

from config.settings import settings


# Thư mục chứa các file workflow JSON
WORKFLOWS_DIR = Path(__file__).resolve().parents[1] / "workflows"


def load_workflow(filename: str) -> Dict[str, Any]:
    """
    Đọc file JSON workflow và trả về dict để ta chỉnh sửa.
    VD: workflow_gen.json, workflow_edit.json
    """
    path = WORKFLOWS_DIR / filename
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_debug_workflow(workflow: Dict[str, Any], filename: str) -> None:
    """
    (Tuỳ chọn) Lưu workflow đã chỉnh để debug trong thư mục workflows/_debug.
    """
    debug_dir = WORKFLOWS_DIR / "_debug"
    debug_dir.mkdir(exist_ok=True)
    path = debug_dir / filename
    with path.open("w", encoding="utf-8") as f:
        json.dump(workflow, f, indent=2, ensure_ascii=False)


def _set_seed_random(workflow: Dict[str, Any]) -> None:
    """
    Tìm node KSampler trong workflow và set seed random (64-bit).
    (Giả sử chỉ có 1 KSampler chính – đúng với workflow của bạn.)
    """
    seed_val = random.randint(0, 2**63 - 1)

    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") == "KSampler":
            inputs = node.get("inputs", {})
            if "seed" in inputs:
                inputs["seed"] = seed_val
                # chỉ chỉnh node KSampler đầu tiên là đủ
                return


def _set_prompt_for_gen(workflow: Dict[str, Any], prompt: str) -> None:
    """
    Với workflow GEN ảnh:
    - Tìm node CLIPTextEncode positive (node có class_type = "CLIPTextEncode"
      và có key "text" trong inputs)
    - Set text = prompt mới
    """
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") == "CLIPTextEncode":
            inputs = node.get("inputs", {})
            if "text" in inputs:
                inputs["text"] = prompt
                return


def _set_prompt_for_edit(workflow: Dict[str, Any], prompt: str) -> None:
    """
    Với workflow EDIT ảnh:
    - Tìm node TextEncodeQwenImageEdit positive
    - Set prompt = prompt mới
    (Giả định node này là node đầu tiên có "prompt" trong inputs)
    """
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") == "TextEncodeQwenImageEdit":
            inputs = node.get("inputs", {})
            if "prompt" in inputs:
                inputs["prompt"] = prompt
                return


def build_gen_workflow(prompt: str, job_id: str) -> Dict[str, Any]:
    """
    Build workflow GEN:
    - Load từ workflow_gen.json
    - Set prompt
    - Random seed
    - Gắn _client_id vào trong workflow để ComfyUI tracking
    """
    wf = load_workflow("gen_image.json")

    # set prompt
    _set_prompt_for_gen(wf, prompt)

    # random seed
    _set_seed_random(wf)

    # gắn _client_id vào trong prompt (đây là convention của ComfyUI)
    # wf["_client_id"] = job_id

    # save_debug_workflow(wf, f"gen_{job_id}.json")  # bật nếu muốn debug
    return wf


def build_edit_workflow(prompt: str, base_image_filename: str, job_id: str) -> Dict[str, Any]:
    """
    Build workflow EDIT:
    - Load từ workflow_edit.json
    - Set prompt vào TextEncodeQwenImageEdit
    - Set ảnh gốc vào LoadImage
    - Random seed
    
    Args:
        prompt: Prompt edit
        base_image_filename: Tên file ảnh (đã có trong ComfyUI input folder)
        job_id: Job ID
    """
    wf = load_workflow("edit_image.json")

    _set_prompt_for_edit(wf, prompt)
    
    # Set filename trực tiếp (không phải URL)
    print(f"[WorkflowBuilder] Setting LoadImage to filename: {base_image_filename}")
    for node_id, node in wf.items():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") in ("LoadImage", "ImageLoader"):
            inputs = node.get("inputs", {})
            if "image" in inputs:
                inputs["image"] = base_image_filename
                print(f"[WorkflowBuilder] Set LoadImage node {node_id} to: {base_image_filename}")
                break
    
    _set_seed_random(wf)

    # save_debug_workflow(wf, f"edit_{job_id[:8]}.json")  # bật nếu muốn debug
    return wf
