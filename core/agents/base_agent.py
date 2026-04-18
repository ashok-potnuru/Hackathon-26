from __future__ import annotations


class BaseAgent:
    """Thin wrapper around ClaudeAdapter for agents with custom system prompts.

    Agents receive the adapter from context["adapters"]["llm"] rather than
    creating their own client, preserving the existing adapter abstraction.
    Uses ephemeral cache_control on the system prompt for cost efficiency.
    """

    def __init__(self, llm_adapter) -> None:
        self._llm = llm_adapter

    def run_turn(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 4096,
    ) -> str:
        resp = self._llm._client.messages.create(
            model=self._llm._model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
        )
        return resp.content[0].text
