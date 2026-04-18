from __future__ import annotations

import json
from dataclasses import dataclass, field

from core.agents.base_agent import BaseAgent

_CODER_SYSTEM = (
    "You are an expert software engineer fixing bugs and implementing features "
    "in a Node.js/JavaScript codebase. You receive file contents and a requirement. "
    "Always return valid JSON only — no markdown fences, no explanation outside the JSON."
)

_CODER_PROMPT = """\
Requirement:
Title: {title}
Description: {description}

Current file contents:
{file_contents_block}

Similar past fixes for context:
{similar_fixes}

{feedback_block}

Generate fixes. Return JSON only:
{{
  "reasoning": "explanation of root cause and approach",
  "files": {{"path/to/file.js": "complete new file content", ...}},
  "regression_test": "test code snippet",
  "confidence": 0.85
}}

Rules:
- Only include files that actually need changes
- Return COMPLETE file contents, not diffs
- confidence is a float between 0.0 and 1.0"""

@dataclass
class CoderResult:
    file_contents: dict[str, str]
    reasoning: str
    confidence: float
    regression_test: str = ""
    raw_response: str = ""


class CoderAgent(BaseAgent):
    def generate(
        self,
        title: str,
        description: str,
        code_context: dict[str, str],
        similar_fixes: str = "",
        reviewer_feedback: str = "",
    ) -> CoderResult:
        """Generate code fixes for files in code_context.

        reviewer_feedback is injected on retry iterations so the model
        addresses the specific issues raised by ReviewerAgent.
        """
        file_contents_block = "\n\n".join(
            f"### {path}\n```javascript\n{content}\n```"
            for path, content in code_context.items()
        )
        feedback_block = (
            f"PREVIOUS ATTEMPT FEEDBACK (fix these issues):\n{reviewer_feedback}"
            if reviewer_feedback
            else ""
        )
        prompt = _CODER_PROMPT.format(
            title=title,
            description=description,
            file_contents_block=file_contents_block,
            similar_fixes=similar_fixes or "No similar fixes available.",
            feedback_block=feedback_block,
        )
        raw = self.run_turn(
            system_prompt=_CODER_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=8192,
        )

        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            data = json.loads(raw[start:end])
        except (ValueError, json.JSONDecodeError):
            return CoderResult(
                file_contents={},
                reasoning="JSON parse failed",
                confidence=0.0,
                raw_response=raw,
            )

        return CoderResult(
            file_contents=data.get("files", {}),
            reasoning=data.get("reasoning", ""),
            confidence=float(data.get("confidence", 0.5)),
            regression_test=data.get("regression_test", ""),
            raw_response=raw,
        )
