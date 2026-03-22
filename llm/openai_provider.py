"""OpenAI LLM provider (works with any OpenAI-compatible API)."""
from __future__ import annotations
import os
from llm import LLMProvider

DEFAULT_MODEL = "gpt-4o"


class OpenAIProvider(LLMProvider):
    """OpenAI via the openai Python SDK. Also works with Azure, Together, etc."""

    def __init__(self, model: str = "", api_key: str = "", base_url: str = "", **kwargs):
        super().__init__(**kwargs)
        self.model = model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key required. Set OPENAI_API_KEY env var "
                "or pass --api-key on the command line."
            )
        import openai
        client_kwargs = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        self.client = openai.OpenAI(**client_kwargs)

    def complete(self, prompt: str, system: str = "") -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=1024,
            temperature=0.3,
        )
        return response.choices[0].message.content
