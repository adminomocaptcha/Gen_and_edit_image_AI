import json
import re
import time
import uuid
from typing import Literal, Optional

import aiohttp

Mode = Literal["NEW", "EDIT"]


class OllamaModeClassifier:
    """
    Dùng Ollama (ví dụ model: 'turbo') để phân loại prompt là NEW hay EDIT.
    """

    def __init__(
        self,
        host: str = "http://127.0.0.1:11434",
        model: str = "turbo",
        api_key: Optional[str] = None,
        request_timeout: float = 10.0,
        dedupe_case_insensitive: bool = True,
    ):
        self.host = host.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.request_timeout = request_timeout
        self.dedupe_case_insensitive = dedupe_case_insensitive

    async def classify_mode(self, prompt: str) -> Mode:
        # Nếu prompt rỗng thì coi như NEW
        if not prompt or not prompt.strip():
            return "NEW"

        sys_prompt = f"""
You are an image-request classifier for an image generation system.

Your job is to read the user's text prompt and decide whether the user is:

1. Asking to CREATE A NEW IMAGE from description (mode = "NEW"), or
2. Asking to EDIT / MODIFY an EXISTING IMAGE (mode = "EDIT").

Rules:

- If the prompt clearly talks about "this image", "the previous image", "given image", 
  or changing/removing/adding elements on an existing picture, choose "EDIT".
- Common edit verbs: edit, remove, erase, delete, change, fix, replace, 
  add something, make the background different, remove text, change color of something, etc.
- If the prompt is only describing a scene or character to generate (without referencing an existing image),
  choose "NEW".

Output STRICTLY in this JSON format, with no extra text:

{{
  "mode": "NEW"
}}

or

{{
  "mode": "EDIT"
}}


"{prompt.strip()}"
        """.strip()

        url = f"{self.host}/api/generate"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "prompt": sys_prompt,
            "stream": False,
        }

        text = ""
        try:
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        # Có thể log body nếu muốn debug
                        body_text = await resp.text()
                        print(
                            f"[OllamaModeClassifier] HTTP {resp.status} from {url}: {body_text[:300]}"
                        )
                        resp.raise_for_status()
                    body = await resp.json()
                    # Ollama trả key "response" (tùy version, kiểm tra lại nếu khác)
                    text = (body or {}).get("response", "") or ""
        except Exception as e:
            print(f"[OllamaModeClassifier] Error calling Ollama: {e}")
            return self._fallback_rule(prompt)

        # Parse JSON trong text trả về
        try:
            # Tìm đoạn JSON trong text (giống code bạn gửi)
            m = re.search(r"\{[\s\S]*\}", text)
            if not m:
                print("[OllamaModeClassifier] No JSON found in response, raw:", text[:200])
                return self._fallback_rule(prompt)

            parsed = json.loads(m.group())
            mode_val = parsed.get("mode", "").strip().upper()
            if mode_val not in ("NEW", "EDIT"):
                return self._fallback_rule(prompt)
            return mode_val  # type: ignore[return-value]
        except Exception as e:
            print(f"[OllamaModeClassifier] Error parsing JSON: {e}, raw={text[:200]}")
            return self._fallback_rule(prompt)


    @staticmethod
    def _fallback_rule(prompt: str) -> Mode:
        """
        Fallback đơn giản nếu LLM bị lỗi:
        """
        p = (prompt or "").lower()
        edit_keywords = [
            "edit",
            "remove",
            "erase",
            "delete",
            "change",
            "fix",
            "replace",
            "add ",
            "add something",
            "make her",
            "make him",
            "remove text",
            "xóa",
            "xoá",
            "sửa",
            "chỉnh",
        ]
        for kw in edit_keywords:
            if kw in p:
                return "EDIT"
        return "NEW"



def gen_job_id() -> str:
    return str(uuid.uuid4())


def get_timestamp_ms() -> int:
    return int(time.time() * 1000)