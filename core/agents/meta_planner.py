from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.agents.base_agent import BaseAgent
from core.utils.json_utils import extract_json

_ROOT = Path(__file__).parent.parent.parent
_API_MD = (_ROOT / "API.md").read_text(encoding="utf-8")
_CMS_MD = (_ROOT / "CMS.md").read_text(encoding="utf-8")

_META_SYSTEM = f"""\
You are the lead architect for a two-repo streaming platform (TV2Z).

=== API REPO (Node.js / Express / JavaScript) ===
{_API_MD}

=== CMS REPO (PHP 8.2 / Laravel 10) ===
{_CMS_MD}

Your job for any incoming requirement:
1. Decide which repo(s) need changes: only "api", only "cms", or both.
2. For each repo, write a PRECISE, focused change spec — exactly what code/data needs to change in that repo only.
3. Extract shared_context: field names, data structures, default values, DB column names that BOTH repos must agree on.
4. Return repos as an ORDERED list — the repo listed first will be implemented first.
   Rule: if CMS writes data that the API reads, put "cms" first.

Always respond with valid JSON only — no markdown, no explanation outside the JSON.
"""

_META_PROMPT = """\
Requirement:
Title: {title}
Description: {description}

Return JSON only:
{{
  "repos": ["cms", "api"],
  "api_spec": "precise description of ONLY what needs to change in the Node.js API repo \
(empty string if api not involved)",
  "cms_spec": "precise description of ONLY what needs to change in the PHP/Laravel CMS repo \
(empty string if cms not involved)",
  "shared_context": "key facts both repos must agree on: exact field names, DB column/table names, \
JSON keys, allowed values, defaults",
  "reasoning": "one sentence explaining the split and ordering"
}}"""


@dataclass
class MetaPlan:
    repos: list[str]          # ordered execution list e.g. ["cms", "api"]
    api_spec: str             # focused spec for API repo (empty if not needed)
    cms_spec: str             # focused spec for CMS repo (empty if not needed)
    shared_context: str       # facts both repos must agree on
    reasoning: str

    def spec_for(self, repo_type: str) -> str:
        return self.api_spec if repo_type == "api" else self.cms_spec


class MetaPlannerAgent(BaseAgent):
    """Stage 0: understands the full requirement and produces per-repo focused specs."""

    def plan(self, title: str, description: str) -> MetaPlan:
        prompt = _META_PROMPT.format(title=title, description=description)
        raw = self.run_turn(
            system_prompt=_META_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
        )
        try:
            data = extract_json(raw)
            repos = [r for r in data.get("repos", ["api"]) if r in ("api", "cms")]
            if not repos:
                repos = ["api"]
            return MetaPlan(
                repos=repos,
                api_spec=str(data.get("api_spec", "")),
                cms_spec=str(data.get("cms_spec", "")),
                shared_context=str(data.get("shared_context", "")),
                reasoning=str(data.get("reasoning", "")),
            )
        except Exception:
            return MetaPlan(
                repos=["api"],
                api_spec=description,
                cms_spec="",
                shared_context="",
                reasoning="meta-planning failed — defaulting to api",
            )
