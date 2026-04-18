from __future__ import annotations

from dataclasses import dataclass, field

from core.agents.base_agent import BaseAgent
from core.constants import MAX_FILES_FOR_AUTO_FIX
from core.utils.graph_navigator import GraphNavigator
from core.utils.json_utils import extract_json

_PLANNER_SYSTEM = (
    "You are a code planning expert. Given a bug report or feature request, "
    "extract concise search keywords that identify the affected code areas. "
    "Always respond with valid JSON only — no markdown, no explanation."
)

_KEYWORD_PROMPT = """\
Issue title: {title}
Issue description: {description}

Extract 3-8 lowercase keywords that would appear as substrings in filenames \
or short code identifiers (function names, class names, model names).

CRITICAL RULES for keywords:
- Use SHORT single words or two-word identifiers: "region", "regions", "auth", "settings"
- NEVER use long compound phrases like "platform_settings_api" or "region_object" — \
  these will not match anything in the codebase
- Think about what the actual variable/function/filename looks like in code
- If the issue involves a database model, include the model name AND "migration"
- If the issue involves an API response, include the route/schema name (e.g. "auth", "settings") \
  NOT generic terms like "api_response"
- If the issue adds fields to a model, also include "schema" and "docs" to find \
  OpenAPI/documentation files that must be updated

Return JSON only: {{"keywords": ["kw1", "kw2", ...], "change_type": "bugfix|feature|refactor"}}"""


@dataclass
class PlanResult:
    target_files: list[str]
    change_type: str
    affected_communities: list[int] = field(default_factory=list)
    keywords_extracted: list[str] = field(default_factory=list)
    reasoning: str = ""


class PlannerAgent(BaseAgent):
    def __init__(self, llm_adapter, graph_navigator: GraphNavigator) -> None:
        super().__init__(llm_adapter)
        self._nav = graph_navigator

    def plan(
        self,
        title: str,
        description: str,
        max_files: int = MAX_FILES_FOR_AUTO_FIX,
    ) -> PlanResult:
        """Extract keywords via LLM, search graph, return files to fix.

        Returns PlanResult(target_files=[]) when graph has no matches,
        signalling the caller to fall back to the original LLM file-listing.
        """
        prompt = _KEYWORD_PROMPT.format(title=title, description=description)
        raw = self.run_turn(
            system_prompt=_PLANNER_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
        )

        try:
            data = extract_json(raw)
            keywords = [str(k).lower() for k in data.get("keywords", []) if k]
            change_type = str(data.get("change_type", "bugfix"))
        except Exception:
            keywords = [w for w in title.lower().split() if len(w) > 2][:5]
            change_type = "bugfix"

        if not keywords:
            return PlanResult(
                target_files=[],
                change_type=change_type,
                keywords_extracted=[],
                reasoning="No keywords could be extracted from the issue.",
            )

        matches = self._nav.search_nodes(keywords, top_k=30)

        if not matches:
            return PlanResult(
                target_files=[],
                change_type=change_type,
                keywords_extracted=keywords,
                reasoning="No graph nodes matched extracted keywords; falling back to LLM file selection.",
            )

        # Deduplicate seed files from top-10 matches; skip doc-only files
        seed_files: list[str] = []
        seen: set[str] = set()
        for m in matches[:10]:
            sf = m.source_file
            if sf and sf not in seen and not sf.endswith(".md"):
                seen.add(sf)
                seed_files.append(sf)
                if len(seed_files) >= 5:
                    break

        related_files = self._nav.get_related_files(seed_files, max_hops=2, max_files=max_files)

        affected_communities = list(dict.fromkeys(
            m.community for m in matches[:10] if m.community not in (-1, 0)
        ))

        return PlanResult(
            target_files=related_files,
            change_type=change_type,
            affected_communities=affected_communities,
            keywords_extracted=keywords,
            reasoning=(
                f"Graph search matched {len(matches)} nodes across {len(seed_files)} seed files. "
                f"BFS expansion yielded {len(related_files)} related files."
            ),
        )
