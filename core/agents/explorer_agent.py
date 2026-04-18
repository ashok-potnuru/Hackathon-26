from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.agents.base_agent import BaseAgent
from core.utils.json_utils import extract_json

_EXPLORER_SYSTEM = """\
You are a read-only code explorer. Your only job is to read code sections and \
identify which parts are directly relevant to a given requirement.

=== CRITICAL: READ-ONLY MODE ===
You are STRICTLY PROHIBITED from suggesting, implying, or writing any code changes.
You do NOT fix, patch, or modify anything. You ONLY identify and label.
Your entire output must be valid JSON — no explanations, no code snippets outside JSON.

Your strengths:
- Identifying which functions/classes are the root cause of an issue
- Distinguishing files that must change from files that are context only
- Pinpointing the exact line ranges that matter
- Recognising when a file is irrelevant and should be excluded entirely\
"""

_EXPLORER_PROMPT = """\
Requirement:
Title: {title}
Description: {description}

The following code sections were retrieved from the repository.
Each section shows file path and line numbers.

{sections}

For each file, identify:
1. Which specific line ranges are DIRECTLY relevant to the requirement
2. What each relevant section does (one sentence)
3. Whether this file definitely needs to change ("must_change") or just provides context ("context_only")

Return JSON only:
{{
  "files": {{
    "path/to/file.js": {{
      "must_change": true,
      "relevant_lines": "42-67, 89-94",
      "reason": "Contains the charge() function that handles payment processing"
    }},
    "path/to/other.js": {{
      "must_change": false,
      "relevant_lines": "1-20",
      "reason": "Exports the PaymentGateway class used by the above file"
    }}
  }},
  "summary": "One sentence describing the root area of the codebase that needs changing"
}}"""


@dataclass
class ExplorerResult:
    must_change_files: dict[str, str]   # {path: relevant_lines string e.g. "42-67, 89-94"}
    context_files: dict[str, str]       # {path: relevant_lines} — context only, no changes needed
    summary: str
    raw_files_analysis: dict            # full JSON from LLM for debugging


def _parse_line_range(range_str: str, full_content: str) -> str:
    """Extract specific lines from file content given a range string like '42-67, 89-94'.

    Handles content that already has N| line-number prefixes (from the graph filter).
    In that case, looks up lines by their actual original-file line number instead of
    treating lines as 1-indexed positions — preventing double-prefix corruption.
    """
    raw_lines = full_content.splitlines()

    # Build a map {original_line_number: bare_text} from N| prefixed content.
    # If no prefixes are found, fall back to positional indexing (1-based).
    line_map: dict[int, str] = {}
    for raw in raw_lines:
        m = re.match(r'^(\d+)\| ?(.*)', raw)
        if m:
            line_map[int(m.group(1))] = m.group(2)

    use_map = bool(line_map)
    positional = [ln for ln in raw_lines if not re.match(r'^(\d+)\| ?|^# lines ', ln)]

    parts: list[str] = []
    for segment in range_str.split(","):
        segment = segment.strip()
        if not segment:
            continue
        try:
            if "-" in segment:
                start_s, end_s = segment.split("-", 1)
                s, e = int(start_s.strip()), int(end_s.strip())
                if use_map:
                    selected = {ln: txt for ln, txt in line_map.items() if s <= ln <= e}
                    if selected:
                        section = "\n".join(
                            f"{ln}| {txt}" for ln, txt in sorted(selected.items())
                        )
                        parts.append(f"# lines {s}–{e}\n{section}")
                else:
                    s, e = max(1, s), min(len(positional), e)
                    section = "\n".join(
                        f"{i}| {positional[i-1]}" for i in range(s, e + 1)
                    )
                    parts.append(f"# lines {s}–{e}\n{section}")
            else:
                ln = int(segment)
                if use_map and ln in line_map:
                    parts.append(f"{ln}| {line_map[ln]}")
                elif not use_map and 1 <= ln <= len(positional):
                    parts.append(f"{ln}| {positional[ln-1]}")
        except (ValueError, IndexError):
            pass

    return "\n\n".join(parts) if parts else full_content[:2000]


class ExplorerAgent(BaseAgent):
    """Read-only agent that identifies exactly which code sections are relevant.

    Sits between GraphNavigator (which gives candidate files + graph-filtered lines)
    and CoderAgent (which writes the fix). ExplorerAgent uses AI judgment to
    further narrow down which sections truly need attention, and marks which
    files must change vs. which are just context.
    """

    def explore(
        self,
        title: str,
        description: str,
        code_sections: dict[str, str],   # {path: graph-filtered content}
    ) -> ExplorerResult:
        """Identify which sections of the provided code are relevant to the requirement.

        code_sections values are already graph-filtered (relevant lines only).
        ExplorerAgent further refines: which files MUST change vs. context only.
        """
        sections_block = "\n\n".join(
            f"=== {path} ===\n{content}"
            for path, content in code_sections.items()
        )
        prompt = _EXPLORER_PROMPT.format(
            title=title,
            description=description,
            sections=sections_block,
        )
        raw = self.run_turn(
            system_prompt=_EXPLORER_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
        )

        try:
            data = extract_json(raw)
        except Exception:
            # Fallback: treat all files as must_change with full content
            return ExplorerResult(
                must_change_files=code_sections,
                context_files={},
                summary="Could not parse explorer response; sending all sections to coder.",
                raw_files_analysis={},
            )

        files_data: dict = data.get("files", {})
        must_change: dict[str, str] = {}
        context_only: dict[str, str] = {}

        for path, info in files_data.items():
            if path not in code_sections:
                continue
            if not isinstance(info, dict):
                must_change[path] = code_sections[path]
                continue
            relevant_lines_str = info.get("relevant_lines", "")
            refined_content = (
                _parse_line_range(relevant_lines_str, code_sections[path])
                if relevant_lines_str
                else code_sections[path]
            )
            if info.get("must_change", True):
                must_change[path] = refined_content
            else:
                context_only[path] = refined_content

        # Any file in code_sections not mentioned by explorer → treat as must_change
        for path in code_sections:
            if path not in must_change and path not in context_only:
                must_change[path] = code_sections[path]

        return ExplorerResult(
            must_change_files=must_change,
            context_files=context_only,
            summary=data.get("summary", ""),
            raw_files_analysis=files_data,
        )
