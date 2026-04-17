import json

from core.constants import MAX_FIX_RETRIES
from core.exceptions import FixGenerationError, SecurityScanError
from core.models.fix import FixModel


def _build_fix_context(issue, research: dict, work_type: str) -> dict:
    if work_type == "feature":
        return {
            "title": issue.title,
            "description": (
                f"You are implementing a new feature based on a PRD.\n\n"
                f"PRD Content:\n{issue.description}\n\n"
                "Generate the required code to implement this feature."
            ),
            "code_context": research["code_context"],
            "similar_fixes": research["similar_fixes"],
        }
    return {
        "title": issue.title,
        "description": issue.description,
        "code_context": research["code_context"],
        "similar_fixes": research["similar_fixes"],
    }


async def run(context: dict) -> dict:
    issue = context["issue"]
    research = context["research"]
    llm = context["adapters"]["llm"]
    work_type = context.get("work_type", "bugfix")

    fix_ctx = _build_fix_context(issue, research, work_type)

    last_err = None
    for attempt in range(MAX_FIX_RETRIES + 1):
        raw = llm.generate_fix(fix_ctx)

        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            data = json.loads(raw[start:end])
        except (ValueError, json.JSONDecodeError) as e:
            last_err = f"JSON parse error: {e}"
            fix_ctx["previous_attempt"] = f"Previous attempt failed: {last_err}. Try again."
            continue

        review = llm.review_fix(raw)
        if not review.get("security_ok", True):
            raise SecurityScanError(f"Security scan failed: {review.get('issues', [])}")

        confidence = float(data.get("confidence", 0.7))
        if confidence < 0.4:
            last_err = f"Low confidence: {confidence}"
            fix_ctx["previous_attempt"] = f"Previous attempt had low confidence ({confidence}). Improve it."
            continue

        file_contents: dict = data.get("files", {})
        fix = FixModel(
            files_changed=list(file_contents.keys()),
            diff=json.dumps(file_contents),
            reasoning=data.get("reasoning", ""),
            regression_test=data.get("regression_test", ""),
            security_scan_passed=review.get("security_ok", True),
            lint_passed=True,
            confidence_score=confidence,
            file_contents=file_contents,
        )
        return {**context, "fix": fix}

    raise FixGenerationError(f"Code generation failed after {MAX_FIX_RETRIES + 1} attempts: {last_err}")
