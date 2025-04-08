# ebay_agent_app/config.py
import os

OLLAMA_BASE_URL = os.environ.get(
    "OLLAMA_BASE_URL", "https://9759-216-113-160-105.ngrok-free.app")
LLM_MODEL = os.environ.get("LLM_MODEL", "mistral")

USER_DATA = {
    "1234567890-98109": {
        "authenticated": True
    },
    "9876543210-12345": {
        "authenticated": True
    }
}
