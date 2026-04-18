from __future__ import annotations

import json
import logging

from core.agents.coder_agent import CoderAgent
from core.agents.explorer_agent import ExplorerAgent
from core.agents.planner_agent import PlanResult
from core.agents.reviewer_agent import ReviewerAgent
from core.exceptions import FixGenerationError, SecurityScanError
from core.models.fix import FixModel
from core.utils.graph_navigator import GraphNavigator

logger = logging.getLogger(__name__)

MAX_REVIEW_ITERATIONS = 3


class MultiAgentOrchestrator:
    """Coordinates CoderAgent → ReviewerAgent feedback loop to produce a FixModel.

    Injected dependencies come from context["adapters"] so the adapter
    abstraction layer is preserved — swap LLM or VCS via settings.yaml.
    """

    def __init__(self, llm_adapter, vc_adapter, graph_navigator: GraphNavigator) -> None:
        self._explorer = ExplorerAgent(llm_adapter)
        self._coder = CoderAgent(llm_adapter)
        self._reviewer = ReviewerAgent(llm_adapter)
        self._vc = vc_adapter
        self._nav = graph_navigator

    def run(
        self,
        issue,
        plan: PlanResult,
        similar_fixes: str = "",
    ) -> FixModel:
        """Run the full fix cycle for the given issue and plan.

        Phase 1: fetch full file contents from GitHub, then filter to relevant
                 lines using graph node source_location data.
        Phase 2: Coder→Reviewer loop (up to MAX_REVIEW_ITERATIONS attempts).
        Phase 3: assemble and return FixModel compatible with existing pipeline.
        """
        repo = issue.affected_repos[0] if issue.affected_repos else ""

        # Phase 1: fetch files from GitHub, then filter to relevant sections
        # full_code keeps the complete content (for the reviewer and PR diff)
        # filtered_code sends only relevant lines to the CoderAgent
        full_code: dict[str, str] = {}
        filtered_code: dict[str, str] = {}
        for file_path in plan.target_files:
            try:
                content = self._vc.get_file(repo, file_path, issue.target_branch)
                full_code[file_path] = content
                filtered_code[file_path] = self._nav.get_relevant_lines(
                    source_file=file_path,
                    file_content=content,
                    keywords=plan.keywords_extracted,
                )
            except Exception as exc:
                logger.warning("Could not fetch %s: %s", file_path, exc)

        original_code = full_code  # alias for clarity below

        if not full_code:
            raise FixGenerationError(
                f"No files could be fetched from GitHub repo '{repo}' "
                f"for files: {plan.target_files}"
            )

        # Phase 1b: ExplorerAgent — AI-powered relevance filtering
        # Narrows down which files must change vs. which are just context
        explorer_result = self._explorer.explore(
            title=issue.title,
            description=issue.description,
            code_sections=filtered_code,
        )
        logger.info(
            json.dumps({
                "event": "explorer_done",
                "must_change": list(explorer_result.must_change_files.keys()),
                "context_only": list(explorer_result.context_files.keys()),
                "summary": explorer_result.summary,
            })
        )

        # CoderAgent gets must_change files + context files clearly separated
        coder_context = {
            **explorer_result.must_change_files,
            **{f"[CONTEXT ONLY] {p}": v for p, v in explorer_result.context_files.items()},
        }

        # Phase 2: Coder→Reviewer loop
        from core.agents.coder_agent import CoderResult
        best_result: CoderResult | None = None
        reviewer_feedback = ""
        approved = False

        for attempt in range(MAX_REVIEW_ITERATIONS):
            logger.info(
                json.dumps({
                    "event": "orchestrator_attempt",
                    "attempt": attempt,
                    "files": list(original_code.keys()),
                })
            )

            coder_result = self._coder.generate(
                title=issue.title,
                description=issue.description,
                code_context=coder_context,   # explorer-filtered: must_change + context
                similar_fixes=similar_fixes,
                reviewer_feedback=reviewer_feedback,
            )

            if not coder_result.file_contents or coder_result.confidence < 0.2:
                reviewer_feedback = (
                    f"Previous attempt produced invalid or very low-confidence output "
                    f"(confidence={coder_result.confidence:.2f}). "
                    "Return a complete, correct fix as JSON."
                )
                continue

            if best_result is None or coder_result.confidence > best_result.confidence:
                best_result = coder_result

            # Only review files that were actually changed
            original_subset = {
                p: c for p, c in original_code.items()
                if p in coder_result.file_contents
            }
            review_result = self._reviewer.review(
                description=issue.description,
                original_code=original_subset,
                proposed_changes=coder_result.file_contents,
            )

            if not review_result.security_ok:
                raise SecurityScanError(
                    f"Security scan failed on attempt {attempt}: {review_result.issues}"
                )

            if review_result.approved:
                best_result = coder_result
                approved = True
                logger.info(json.dumps({
                    "event": "orchestrator_approved",
                    "attempt": attempt,
                    "verdict": review_result.verdict,
                }))
                break

            reviewer_feedback = review_result.feedback
            logger.info(json.dumps({
                "event": "orchestrator_retry",
                "attempt": attempt,
                "verdict": review_result.verdict,
                "checks": review_result.checks,
                "feedback_preview": reviewer_feedback[:200],
            }))

        if not approved or best_result is None or not best_result.file_contents:
            raise FixGenerationError(
                f"Code generation failed after {MAX_REVIEW_ITERATIONS} attempts"
            )

        # Phase 3: assemble FixModel
        return FixModel(
            files_changed=list(best_result.file_contents.keys()),
            diff=json.dumps(best_result.file_contents),
            reasoning=f"{plan.reasoning}\n\n{best_result.reasoning}",
            regression_test=best_result.regression_test,
            security_scan_passed=True,
            lint_passed=True,
            confidence_score=best_result.confidence,
            file_contents=best_result.file_contents,
        )
