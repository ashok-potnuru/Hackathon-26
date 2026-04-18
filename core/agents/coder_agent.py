from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.agents.base_agent import BaseAgent
from core.utils.json_utils import extract_json

_CODER_SYSTEM_API = (
    "You are an expert Node.js/JavaScript engineer fixing bugs and implementing features "
    "in an Express.js REST API codebase. You receive file contents and a requirement. "
    "Always return valid JSON only — no markdown fences, no explanation outside the JSON."
)

_CODER_SYSTEM_CMS = (
    "You are an expert PHP 8.2/Laravel 10 engineer fixing bugs and implementing features "
    "in a Laravel CMS codebase. Follow Laravel conventions: use Eloquent ORM, Artisan commands, "
    "Blade views, Livewire components, and Stancl/Tenancy multi-tenant patterns. "
    "When adding database fields, include the corresponding migration file. "
    "Always return valid JSON only — no markdown fences, no explanation outside the JSON."
)

# Legacy default — kept for backward compat
_CODER_SYSTEM = _CODER_SYSTEM_API

_LANG_FENCE = {"api": "javascript", "cms": "php"}

_CODER_PROMPT = """\
Requirement:
Title: {title}
Description: {description}

Current file contents (read these carefully before generating edits):
{file_contents_block}

Similar past fixes for context:
{similar_fixes}

{feedback_block}

Generate SURGICAL edits — do NOT rewrite entire files.
For each change, provide the exact lines to find and what to replace them with.

Return JSON only:
{{
  "reasoning": "explanation of root cause and approach",
  "edits": [
    {{
      "path": "path/to/file.js",
      "old_string": "exact existing lines from the file (include 2-3 lines of context to be unique)",
      "new_string": "replacement lines (same indentation as original)"
    }},
    ...
  ],
  "regression_test": "test code snippet",
  "confidence": 0.85
}}

Rules:
- old_string MUST be copied EXACTLY from the file content shown above (same whitespace, same indentation)
- old_string must include enough surrounding lines to be unique in the file
- new_string must preserve the same indentation style as the surrounding code
- Only include edits for lines that actually need to change — do NOT include unchanged lines
- For adding new fields to an object, old_string should be the last existing field + closing brace/bracket
- confidence is a float between 0.0 and 1.0
- If old_string cannot be found uniquely, include more context lines"""


def strip_line_numbers(content: str) -> str:
    """Remove 'N| ' line number prefixes added by get_relevant_lines/graph navigator.

    Converts:
        '1| const x = 1;\n2| const y = 2;'
    To:
        'const x = 1;\nconst y = 2;'

    Also strips section headers like '# lines 1-47'.
    """
    lines = []
    for line in content.split("\n"):
        # Skip section headers like "# lines 1–47"
        if re.match(r"^# lines \d+", line):
            continue
        # Strip "N| " prefix (handles any number of digits)
        stripped = re.sub(r"^\d+\| ?", "", line)
        lines.append(stripped)
    return "\n".join(lines)


def _apply_edits(edits: list[dict], base_files: dict[str, str]) -> dict[str, str]:
    """Apply old_string → new_string replacements to base_files (full original content).

    base_files must contain the FULL original file content (no line number prefixes).
    Each edit is applied in order; if a file is edited multiple times the second
    edit operates on the already-patched version.
    """
    result: dict[str, str] = {}

    for edit in edits:
        path = edit.get("path", "")
        old_string = edit.get("old_string", "")
        new_string = edit.get("new_string", "")

        if not path or not old_string:
            continue

        # Use already-patched version if this file was edited earlier in the loop
        content = result.get(path) or base_files.get(path, "")

        if old_string in content:
            result[path] = content.replace(old_string, new_string, 1)
        else:
            # Normalize quotes (straight ↔ curly) and retry — same as openclaude findActualString
            def normalize_quotes(s: str) -> str:
                return (s.replace("\u2018", "'").replace("\u2019", "'")
                         .replace("\u201c", '"').replace("\u201d", '"'))

            norm_old = normalize_quotes(old_string)
            norm_content = normalize_quotes(content)

            if norm_old in norm_content:
                idx = norm_content.index(norm_old)
                actual_old = content[idx: idx + len(old_string)]
                result[path] = content.replace(actual_old, new_string, 1)
            else:
                # Could not match — keep the full original so we never commit a truncated file
                result[path] = content

    return result


@dataclass
class CoderResult:
    file_contents: dict[str, str]   # full file contents after surgical edits applied
    reasoning: str
    confidence: float
    regression_test: str = ""
    raw_response: str = ""
    edits: list[dict] = field(default_factory=list)


class CoderAgent(BaseAgent):
    def generate(
        self,
        title: str,
        description: str,
        code_context: dict[str, str],       # explorer-filtered content (may have line numbers)
        similar_fixes: str = "",
        reviewer_feedback: str = "",
        base_files: dict[str, str] | None = None,  # full original files for applying edits
        repo_type: str = "api",
    ) -> CoderResult:
        """Generate surgical code edits.

        code_context  — what the LLM sees (explorer-filtered, stripped of line numbers)
        base_files    — full original file content used as the base for str_replace
                        If omitted, code_context is used as the base (backward-compatible).
        """
        system_prompt = _CODER_SYSTEM_CMS if repo_type == "cms" else _CODER_SYSTEM_API
        lang_fence = _LANG_FENCE.get(repo_type, "javascript")

        # Strip line number prefixes so the LLM sees clean code and its old_string
        # values will match the real file content
        clean_context = {
            path: strip_line_numbers(content)
            for path, content in code_context.items()
        }

        file_contents_block = "\n\n".join(
            f"### {path}\n```{lang_fence}\n{content}\n```"
            for path, content in clean_context.items()
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
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=8192,
        )

        try:
            data = extract_json(raw)
        except Exception:
            return CoderResult(
                file_contents={},
                reasoning="JSON parse failed",
                confidence=0.0,
                raw_response=raw,
            )

        edits: list[dict] = data.get("edits", [])

        # Build the base for applying edits:
        # Priority: base_files (full originals) > clean_context (stripped line numbers)
        # Strip [CONTEXT] prefix from keys in both cases
        def strip_context_prefix(d: dict) -> dict:
            return {p.replace("[CONTEXT] ", ""): c for p, c in d.items()}

        apply_base = strip_context_prefix(base_files) if base_files else strip_context_prefix(clean_context)

        file_contents = _apply_edits(edits, apply_base)

        return CoderResult(
            file_contents=file_contents,
            reasoning=data.get("reasoning", ""),
            confidence=float(data.get("confidence", 0.5)),
            regression_test=data.get("regression_test", ""),
            raw_response=raw,
            edits=edits,
        )
