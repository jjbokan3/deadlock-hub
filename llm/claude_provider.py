"""Anthropic Claude LLM provider."""
from __future__ import annotations
import os
from llm import LLMProvider

DEFAULT_MODEL = "claude-sonnet-4-20250514"


class ClaudeProvider(LLMProvider):
    """Claude via the Anthropic Python SDK."""

    def __init__(self, model: str = "", api_key: str = "", **kwargs):
        super().__init__(**kwargs)
        self.model = model or os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "Anthropic API key required. Set ANTHROPIC_API_KEY env var "
                "or pass --api-key on the command line."
            )
        import anthropic
        self.client = anthropic.Anthropic(api_key=self.api_key)

    def complete(self, prompt: str, system: str = "") -> str:
        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system or "You are a helpful assistant.",
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
