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
2. For each repo, write a PRECISE, focused change spec — exactly what code/data
   needs to change in that repo only.
3. Extract shared_context: field names, data structures, default values, DB column
   names that BOTH repos must agree on.
4. Return repos as an ORDERED list — the repo listed first is implemented first.
   Rule: if CMS writes data that the API reads, put "cms" first.
5. For each repo, provide search keywords that will locate the RUNTIME files that
   need changing — NOT docs, NOT migrations, NOT schemas unless the task is
   specifically about those.
   - CRITICAL: keywords must match FILENAMES or CLASS NAMES in the graph, not function
     names inside files (internal functions are not indexed as graph nodes).
   - For CMS (PHP/Laravel): use controller class names ("RegionController"), blade view
     file names ("manage-region", "edit-region", "add-region"), model names ("Region").
     PHP classes ARE graph nodes, so class names work as keywords.
   - For API (Node.js): use FILE STEM names without extensions — the Node.js graph only
     has file-level nodes, NOT function-level nodes. Use "user_auth_service",
     "user_auth_dal", "user_auth_controller" — NOT function names like "platformV3Settings".
     Think: "what file CONTAINS the function I need to change?"
   - NEVER include "docs", "schema", "migration", "seeder", "config" as keywords unless
     the change is ONLY about those files.

Always respond with valid JSON only — no markdown, no explanation outside the JSON.
"""

_META_PROMPT = """\
Requirement:
Title: {title}
Description: {description}

Return JSON only:
{{
  "repos": ["cms", "api"],
  "api_spec": "precise description of ONLY what needs to change in the Node.js API \
repo (empty string if api not involved)",
  "cms_spec": "precise description of ONLY what needs to change in the PHP/Laravel \
CMS repo (empty string if cms not involved)",
  "api_keywords": ["short", "identifiers", "for", "runtime", "api", "files"],
  "cms_keywords": ["short", "identifiers", "for", "runtime", "cms", "files"],
  "shared_context": "key facts both repos must agree on: exact field names, DB \
column/table names, JSON keys, allowed values, defaults",
  "reasoning": "one sentence explaining the split and ordering"
}}"""


@dataclass
class MetaPlan:
    repos: list[str]                    # ordered execution list e.g. ["cms", "api"]
    api_spec: str                       # focused spec for API repo (empty if not needed)
    cms_spec: str                       # focused spec for CMS repo (empty if not needed)
    api_keywords: list[str]             # runtime-focused search keywords for API graph
    cms_keywords: list[str]             # runtime-focused search keywords for CMS graph
    shared_context: str                 # facts both repos must agree on
    reasoning: str

    def spec_for(self, repo_type: str) -> str:
        return self.api_spec if repo_type == "api" else self.cms_spec

    def keywords_for(self, repo_type: str) -> list[str]:
        return self.api_keywords if repo_type == "api" else self.cms_keywords


class MetaPlannerAgent(BaseAgent):
    """Stage 0: understands the full requirement and produces per-repo focused specs
    and runtime-focused graph search keywords."""

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
                api_keywords=[str(k) for k in data.get("api_keywords", [])],
                cms_keywords=[str(k) for k in data.get("cms_keywords", [])],
                shared_context=str(data.get("shared_context", "")),
                reasoning=str(data.get("reasoning", "")),
            )
        except Exception:
            return MetaPlan(
                repos=["api"],
                api_spec=description,
                cms_spec="",
                api_keywords=[],
                cms_keywords=[],
                shared_context="",
                reasoning="meta-planning failed — defaulting to api",
            )
