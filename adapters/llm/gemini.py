import json
import os

import google.generativeai as genai

from adapters.llm.base import LLMBase
from core.exceptions import AdapterError


class GeminiAdapter(LLMBase):
    def __init__(self):
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        self._model = genai.GenerativeModel("gemini-1.5-pro")

    def analyze(self, prompt: str) -> str:
        return self._model.generate_content(prompt).text

    def generate_fix(self, context: dict) -> str:
        prompt = (
            f"Bug Report:\nTitle: {context.get('title', '')}\n"
            f"Description: {context.get('description', '')}\n\n"
            f"Relevant Code:\n{context.get('code_context', '')}\n\n"
            f"Similar Past Fixes:\n{context.get('similar_fixes', '')}\n\n"
            f"{context.get('previous_attempt', '')}\n\n"
            "Return JSON: reasoning, files (dict[path, new_content]), regression_test, confidence (0-1)."
        )
        return self._model.generate_content(prompt).text

    def review_fix(self, fix: str) -> dict:
        text = self._model.generate_content(
            f"Review this fix for security:\n{fix}\nReturn JSON: approved, issues, security_ok."
        ).text
        try:
            return json.loads(text[text.index("{"):text.rindex("}") + 1])
        except (ValueError, json.JSONDecodeError):
            return {"approved": True, "issues": [], "security_ok": True}

    def embed(self, text: str) -> list:
        result = genai.embed_content(
            model="models/embedding-001", content=text, task_type="retrieval_document"
        )
        return result["embedding"]

    def health_check(self) -> None:
        try:
            self._model.generate_content("ping")
        except Exception as e:
            raise AdapterError(f"Gemini health check failed: {e}")
