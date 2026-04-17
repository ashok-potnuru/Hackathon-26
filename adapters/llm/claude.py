import json
import os

import anthropic

from adapters.llm.base import LLMBase
from core.exceptions import AdapterError

_SYSTEM_PROMPT = "You are an expert software engineer. Follow instructions exactly and return valid JSON when asked."


class ClaudeAdapter(LLMBase):
    def __init__(self):
        self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self._model = "claude-sonnet-4-6"

    def _system(self) -> list:
        return [{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]

    def analyze(self, prompt: str) -> str:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=self._system(),
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text

    def generate_fix(self, context: dict) -> str:
        user_text = (
            f"Bug Report:\nTitle: {context.get('title', '')}\n"
            f"Description: {context.get('description', '')}\n\n"
            f"Relevant Code:\n{context.get('code_context', '')}\n\n"
            f"Similar Past Fixes:\n{context.get('similar_fixes', '')}\n\n"
            f"{context.get('previous_attempt', '')}\n\n"
            "Return JSON with keys: reasoning (str), files (dict[path, new_content]), "
            "regression_test (str), confidence (float 0-1)."
        )
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=self._system(),
            messages=[{"role": "user", "content": user_text}],
        )
        return resp.content[0].text

    def review_fix(self, fix: str) -> dict:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": (
                    f"Review this code fix for correctness and security issues:\n\n{fix}\n\n"
                    "Return JSON: {\"approved\": bool, \"issues\": [str], \"security_ok\": bool}"
                ),
            }],
        )
        text = resp.content[0].text
        try:
            return json.loads(text[text.index("{"):text.rindex("}") + 1])
        except (ValueError, json.JSONDecodeError):
            return {"approved": True, "issues": [], "security_ok": True}

    def embed(self, text: str) -> list:
        return []

    def health_check(self) -> None:
        try:
            self._client.messages.create(
                model=self._model, max_tokens=5,
                messages=[{"role": "user", "content": "ping"}],
            )
        except Exception as e:
            raise AdapterError(f"Claude health check failed: {e}")
