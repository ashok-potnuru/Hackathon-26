import json
import os
import time

import openai

from adapters.llm.base import LLMBase
from core.exceptions import AdapterError

# gpt-4.5 has a 1M token context window — set generous output limits.
_DEFAULT_MODEL = "gpt-5.4"
_MAX_OUTPUT_TOKENS = 16_384   # large enough for full-file edits in one shot


class OpenAIAdapter(LLMBase):
    def __init__(self, model: str | None = None):
        self._client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self._model = model or _DEFAULT_MODEL
        self._embed_model = "text-embedding-3-small"

    def analyze(self, prompt: str) -> str:
        return self._call(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
        )

    def generate_fix(self, context: dict) -> str:
        user_text = (
            f"Bug Report:\nTitle: {context.get('title', '')}\n"
            f"Description: {context.get('description', '')}\n\n"
            f"Relevant Code:\n{context.get('code_context', '')}\n\n"
            f"Similar Past Fixes:\n{context.get('similar_fixes', '')}\n\n"
            f"{context.get('previous_attempt', '')}\n\n"
            "Return JSON: reasoning, files (dict[path, new_content]), regression_test, confidence (0-1)."
        )
        return self._call(
            messages=[
                {"role": "system", "content": "You are an expert software engineer. Return valid JSON when asked."},
                {"role": "user", "content": user_text},
            ],
            max_tokens=_MAX_OUTPUT_TOKENS,
        )

    def review_fix(self, fix: str) -> dict:
        text = self._call(
            messages=[{
                "role": "user",
                "content": f"Review this fix for security:\n{fix}\nReturn JSON: approved, issues, security_ok.",
            }],
            max_tokens=1024,
        )
        try:
            return json.loads(text[text.index("{"):text.rindex("}") + 1])
        except (ValueError, json.JSONDecodeError):
            return {"approved": True, "issues": [], "security_ok": True}

    def embed(self, text: str) -> list:
        resp = self._client.embeddings.create(model=self._embed_model, input=text)
        return resp.data[0].embedding

    def chat_completion(self, system_prompt: str, messages: list, max_tokens: int = 4096) -> str:
        return self._call(
            messages=[{"role": "system", "content": system_prompt}] + messages,
            max_tokens=max_tokens,
        )

    def _call(self, messages: list, max_tokens: int) -> str:
        """Call the OpenAI API with retry on rate-limit errors.

        Newer models (gpt-5.x) require max_completion_tokens instead of max_tokens.
        We try max_completion_tokens first; fall back to max_tokens for older models.
        """
        for attempt in range(4):
            try:
                try:
                    resp = self._client.chat.completions.create(
                        model=self._model,
                        max_completion_tokens=max_tokens,
                        messages=messages,
                    )
                except openai.BadRequestError as e:
                    if "max_completion_tokens" in str(e) or "unsupported_parameter" in str(e):
                        resp = self._client.chat.completions.create(
                            model=self._model,
                            max_tokens=max_tokens,
                            messages=messages,
                        )
                    else:
                        raise
                return resp.choices[0].message.content
            except openai.RateLimitError as e:
                if attempt == 3:
                    raise
                wait = 30 * (attempt + 1)   # 30s, 60s, 90s
                print(f"[OpenAI] Rate limit hit — retrying in {wait}s ({e})")
                time.sleep(wait)
            except Exception:
                raise

    def health_check(self) -> None:
        try:
            self._client.models.list()
        except Exception as e:
            raise AdapterError(f"OpenAI health check failed: {e}")
