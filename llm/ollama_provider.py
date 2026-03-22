"""Ollama provider for local LLM inference."""
from __future__ import annotations
import os
import requests
from llm import LLMProvider

DEFAULT_MODEL = "llama3.1"
DEFAULT_URL = "http://localhost:11434"


class OllamaProvider(LLMProvider):
    """Ollama via its REST API. No SDK dependency — just requests."""

    def __init__(self, model: str = "", base_url: str = "", **kwargs):
        super().__init__(**kwargs)
        self.max_calls = 999999  # local model, no cost concern
        self.model = model or os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)
        self.base_url = (base_url or os.getenv("OLLAMA_URL", DEFAULT_URL)).rstrip("/")

    def complete(self, prompt: str, system: str = "") -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system or "You are a helpful assistant.",
            "stream": False,
            "options": {"temperature": 0.3},
        }
        resp = requests.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")
