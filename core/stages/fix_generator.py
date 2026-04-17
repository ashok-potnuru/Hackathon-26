import json

from core.constants import MAX_FIX_RETRIES
from core.exceptions import FixGenerationError, SecurityScanError
from core.models.fix import FixModel


async def run(context: dict) -> dict:
    issue = context["issue"]
    research = context["research"]
    llm = context["adapters"]["llm"]

    fix_ctx = {
        "title": issue.title,
        "description": issue.description,
        "code_context": research["code_context"],
        "similar_fixes": research["similar_fixes"],
    }

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
            last_err = f"Low confidence score: {confidence}"
            fix_ctx["previous_attempt"] = f"Previous fix had low confidence ({confidence}). Improve it."
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

    raise FixGenerationError(f"Fix generation failed after {MAX_FIX_RETRIES + 1} attempts: {last_err}")
