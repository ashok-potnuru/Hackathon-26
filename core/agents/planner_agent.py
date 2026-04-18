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

{cross_repo_block}
Extract 3-8 lowercase keywords that will locate the RUNTIME source files that \
need to change — controllers, services, models, view templates.

CRITICAL RULES:
- Use SHORT identifiers that appear as substrings in filenames or code: \
  "region", "auth", "platform_settings"
- Think: "what is the function/class/controller that ACTUALLY handles this feature?"
- Prefer the specific handler name over generic words: \
  "platformV3Settings" beats "settings"; "RegionController" beats "controller"
- NEVER include "docs", "schema", "migration", "seeder" — those pull documentation \
  and DB files instead of runtime code, even when those files exist in the repo
- NEVER use long compound phrases — they will not substring-match anything
- For a new field on a model: include the model name + the controller/service that \
  saves/reads it

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
        cross_repo_context: str = "",
        seed_keywords: list[str] | None = None,
        max_files: int = MAX_FILES_FOR_AUTO_FIX,
    ) -> PlanResult:
        """Extract keywords via LLM, search graph, return files to fix.

        seed_keywords: runtime-focused keywords from MetaPlannerAgent — merged with
                       LLM-extracted keywords and tried first in graph search.
        cross_repo_context: summary of what the other repo's pipeline already planned/did.
        Returns PlanResult(target_files=[]) when graph has no matches.
        """
        cross_repo_block = (
            f"Cross-repo context (other repo already handled these changes — "
            f"align field names and data structures):\n{cross_repo_context}\n"
            if cross_repo_context
            else ""
        )
        prompt = _KEYWORD_PROMPT.format(
            title=title,
            description=description,
            cross_repo_block=cross_repo_block,
        )
        raw = self.run_turn(
            system_prompt=_PLANNER_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
        )

        try:
            data = extract_json(raw)
            llm_keywords = [str(k).lower() for k in data.get("keywords", []) if k]
            change_type = str(data.get("change_type", "bugfix"))
        except Exception:
            llm_keywords = [w for w in title.lower().split() if len(w) > 2][:5]
            change_type = "bugfix"

        # Merge MetaPlanner seed keywords (high-signal) in front of LLM keywords.
        # Deduplicate while preserving order so seeds are tried first in graph search.
        seen: set[str] = set()
        keywords: list[str] = []
        for kw in (seed_keywords or []) + llm_keywords:
            kw = kw.lower()
            if kw and kw not in seen:
                seen.add(kw)
                keywords.append(kw)

        if not keywords:
            return PlanResult(
                target_files=[],
                change_type=change_type,
                keywords_extracted=[],
                reasoning="No keywords could be extracted from the issue.",
            )

        # Non-runtime paths that must never seed BFS — they crowd out real controllers.
        _SKIP_PREFIXES = (
            "database/migrations/", "database/seeders/", "database/factories/",
            "docs/", "storage/", "tests/", "test/", "spec/",
            "configs/",   # Node.js config constants — not where features are implemented
        )
        _SKIP_SUFFIXES = (".md", "Schema.js", "schema.js")

        def _is_runtime(sf: str) -> bool:
            return (
                sf
                and not any(sf.endswith(s) for s in _SKIP_SUFFIXES)
                and not any(sf.startswith(p) for p in _SKIP_PREFIXES)
            )

        # Phase 1: search with MetaPlanner seed keywords only — these name specific
        # controllers/views so they win over broad LLM keywords like "configurations".
        seed_kw_list = [k.lower() for k in (seed_keywords or [])]
        seen_sf: set[str] = set()
        phase1: list[str] = []
        if seed_kw_list:
            seed_matches = self._nav.search_nodes(seed_kw_list, top_k=30)
            for m in seed_matches:
                sf = m.source_file
                if sf and sf not in seen_sf and _is_runtime(sf):
                    seen_sf.add(sf)
                    phase1.append(sf)

        # Phase 2: combined search (seed + LLM keywords) for remaining slots.
        all_matches = self._nav.search_nodes(keywords, top_k=40)
        if not all_matches and not phase1:
            return PlanResult(
                target_files=[],
                change_type=change_type,
                keywords_extracted=keywords,
                reasoning="No graph nodes matched extracted keywords; falling back to LLM file selection.",
            )

        phase2: list[str] = []
        for m in all_matches:
            sf = m.source_file
            if sf and sf not in seen_sf and _is_runtime(sf):
                seen_sf.add(sf)
                phase2.append(sf)

        matches = all_matches or seed_matches if seed_kw_list else all_matches
        seed_files = (phase1 + phase2)[:8]

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
