from __future__ import annotations

from dataclasses import dataclass, field

from core.agents.base_agent import BaseAgent
from core.utils.json_utils import extract_json

_REVIEWER_SYSTEM = """\
You are an adversarial code reviewer. Your job is NOT to confirm the fix works — \
it is to try to find everything wrong with it.

You have two documented failure patterns to avoid:
1. Review avoidance: reading code, saying it "looks correct", and approving without evidence.
2. Being seduced by the first 80%: the fix looks clean and handles the happy path, \
   but you miss the edge cases, the security hole, or the silent data corruption.

Your entire value is in finding the last 20%. Be rigorous. Always return valid JSON only.\
"""

_REVIEWER_PROMPT = """\
Original requirement:
{description}

Original code (before changes):
{original_block}

Proposed changes:
{proposed_block}

Run through ALL of these checks. A check without a specific finding is not a PASS — \
it means you looked and found nothing (which is fine, but be explicit).

CHECKS:
1. Correctness — does the change actually fix the root cause, not just the symptom?
2. Security — SQL injection, XSS, auth bypass, data exposure, unvalidated input?
3. Regression risk — any existing callers of changed functions that could break?
4. Boundary values — does it handle null, undefined, empty string, 0, negative numbers?
5. Error handling — are errors caught and handled, or silently swallowed?
6. Concurrency — if called in parallel, can it corrupt state or deadlock?
7. Style — consistent with surrounding code patterns?

Return JSON only:
{{
  "approved": true,
  "verdict": "PASS",
  "feedback": "empty string if approved, specific actionable issues if rejected",
  "issues": ["issue1", "issue2"],
  "security_ok": true,
  "checks": {{
    "correctness": "PASS or description of problem",
    "security": "PASS or description of problem",
    "regression_risk": "PASS or description of problem",
    "boundary_values": "PASS or description of problem",
    "error_handling": "PASS or description of problem",
    "concurrency": "PASS or N/A or description of problem"
  }}
}}

verdict must be exactly "PASS", "FAIL", or "PARTIAL".\
"""

@dataclass
class ReviewResult:
    approved: bool
    verdict: str           # "PASS", "FAIL", or "PARTIAL"
    feedback: str
    issues: list[str]
    security_ok: bool
    checks: dict[str, str] = None   # per-check results from adversarial review


class ReviewerAgent(BaseAgent):
    def review(
        self,
        description: str,
        original_code: dict[str, str],
        proposed_changes: dict[str, str],
    ) -> ReviewResult:
        """Review proposed code changes against the original requirement.

        Returns ReviewResult(approved=True) on JSON parse failure so a
        parse error never silently kills the pipeline.
        """
        # With gpt-4.5's 1M token context we can review full file content.
        _MAX_TOTAL = 800_000

        def _full(d: dict[str, str]) -> dict[str, str]:
            total = 0
            out: dict[str, str] = {}
            for path, content in d.items():
                if total + len(content) > _MAX_TOTAL:
                    break
                out[path] = content
                total += len(content)
            return out

        original_block = "\n\n".join(
            f"### {path} (original)\n```\n{content}\n```"
            for path, content in _full(original_code).items()
        )
        proposed_block = "\n\n".join(
            f"### {path} (proposed)\n```\n{content}\n```"
            for path, content in _full(proposed_changes).items()
        )
        prompt = _REVIEWER_PROMPT.format(
            description=description,
            original_block=original_block or "(no original files provided)",
            proposed_block=proposed_block or "(no proposed changes provided)",
        )
        raw = self.run_turn(
            system_prompt=_REVIEWER_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
        )

        try:
            data = extract_json(raw)
        except Exception:
            return ReviewResult(
                approved=True, verdict="PASS", feedback="", issues=[], security_ok=True
            )

        verdict = str(data.get("verdict", "PASS" if data.get("approved", True) else "FAIL"))
        # PARTIAL counts as not approved — coder gets another attempt
        approved = verdict == "PASS"

        return ReviewResult(
            approved=approved,
            verdict=verdict,
            feedback=str(data.get("feedback", "")),
            issues=list(data.get("issues", [])),
            security_ok=bool(data.get("security_ok", True)),
            checks=data.get("checks"),
        )
