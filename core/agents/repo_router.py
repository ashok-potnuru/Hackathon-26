from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from core.agents.base_agent import BaseAgent
from core.utils.json_utils import extract_json

_ROOT = Path(__file__).parent.parent.parent
_API_MD = (_ROOT / "API.md").read_text(encoding="utf-8")
_CMS_MD = (_ROOT / "CMS.md").read_text(encoding="utf-8")

_ROUTER_SYSTEM = f"""\
You are a code-routing expert for a two-repo streaming platform (TV2Z).

=== API REPO (Node.js / Express / JavaScript) ===
{_API_MD}

=== CMS REPO (PHP 8.2 / Laravel 10) ===
{_CMS_MD}

Given an issue, decide which repo(s) need changes:
- "api"  — only the Node.js API repo
- "cms"  — only the PHP/Laravel CMS repo
- "both" — changes required in both repos

When target is "both", also produce focused sub-task descriptions for each repo.
Always respond with valid JSON only — no markdown, no explanation outside the JSON.
"""

_ROUTER_PROMPT = """\
Issue title: {title}
Issue description: {description}

Return JSON only:
{{
  "target": "api" | "cms" | "both",
  "reasoning": "one sentence explaining why",
  "api_subtask": "what specifically needs changing in the API repo (empty string if not api)",
  "cms_subtask": "what specifically needs changing in the CMS repo (empty string if not cms)"
}}"""


@dataclass
class RouteResult:
    target: Literal["api", "cms", "both"]
    reasoning: str
    api_subtask: str = ""
    cms_subtask: str = ""


class RepoRouter(BaseAgent):
    """Routes an incoming issue to the correct repo(s) using LLM + API.md/CMS.md context."""

    def route(self, title: str, description: str) -> RouteResult:
        prompt = _ROUTER_PROMPT.format(title=title, description=description)
        raw = self.run_turn(
            system_prompt=_ROUTER_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
        )
        try:
            data = extract_json(raw)
            target = str(data.get("target", "api")).lower()
            if target not in ("api", "cms", "both"):
                target = "api"
            return RouteResult(
                target=target,  # type: ignore[arg-type]
                reasoning=str(data.get("reasoning", "")),
                api_subtask=str(data.get("api_subtask", "")),
                cms_subtask=str(data.get("cms_subtask", "")),
            )
        except Exception:
            return RouteResult(target="api", reasoning="routing failed — defaulting to api")
