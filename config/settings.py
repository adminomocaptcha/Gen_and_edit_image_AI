import os
from pathlib import Path
from dotenv import load_dotenv

# Load biến môi trường trong .env
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

class Settings:
    COMFYUI_URL: str = "http://127.0.0.1:8188"
    
    COMFYUI_INPUT_DIR: str = "E:\comfyUI\ComfyUI\input"

    REDIS_URL: str = "redis://127.0.0.1:6379/0"

    OLLAMA_HOST: str = "https://ollama.com"
    OLLAMA_MODEL: str = "gpt-oss:120b"

    OLLAMA_API_KEY: str | None = os.getenv("OLLAMA_API_KEY")
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")

    POLL_INTERVAL: float = 0.5  # giây

settings = Settings()