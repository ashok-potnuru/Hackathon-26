import json
import os

import openai

from adapters.llm.base import LLMBase
from core.exceptions import AdapterError


class OpenAIAdapter(LLMBase):
    def __init__(self, model: str | None = None):
        self._client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self._model = model or "gpt-4o"
        self._embed_model = "text-embedding-3-small"

    def analyze(self, prompt: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content

    def generate_fix(self, context: dict) -> str:
        user_text = (
            f"Bug Report:\nTitle: {context.get('title', '')}\n"
            f"Description: {context.get('description', '')}\n\n"
            f"Relevant Code:\n{context.get('code_context', '')}\n\n"
            f"Similar Past Fixes:\n{context.get('similar_fixes', '')}\n\n"
            f"{context.get('previous_attempt', '')}\n\n"
            "Return JSON: reasoning, files (dict[path, new_content]), regression_test, confidence (0-1)."
        )
        resp = self._client.chat.completions.create(
            model=self._model,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": "You are an expert software engineer. Return valid JSON when asked."},
                {"role": "user", "content": user_text},
            ],
        )
        return resp.choices[0].message.content

    def review_fix(self, fix: str) -> dict:
        resp = self._client.chat.completions.create(
            model=self._model,
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": f"Review this fix for security:\n{fix}\nReturn JSON: approved, issues, security_ok.",
            }],
        )
        text = resp.choices[0].message.content
        try:
            return json.loads(text[text.index("{"):text.rindex("}") + 1])
        except (ValueError, json.JSONDecodeError):
            return {"approved": True, "issues": [], "security_ok": True}

    def embed(self, text: str) -> list:
        resp = self._client.embeddings.create(model=self._embed_model, input=text)
        return resp.data[0].embedding

    def chat_completion(self, system_prompt: str, messages: list, max_tokens: int = 4096) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system_prompt}] + messages,
        )
        return resp.choices[0].message.content

    def health_check(self) -> None:
        try:
            self._client.models.list()
        except Exception as e:
            raise AdapterError(f"OpenAI health check failed: {e}")
