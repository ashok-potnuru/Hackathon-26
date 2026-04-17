from core.constants import ZohoStatus
from core.exceptions import IssueVagueError


async def run(context: dict) -> dict:
    payload = context["payload"]
    adapters = context["adapters"]
    issue_tracker = adapters["issue_tracker"]
    llm = adapters["llm"]

    issue_id = str(payload.get("issue_id") or payload.get("ticketId") or payload.get("id", ""))
    issue = issue_tracker.get_issue(issue_id)
    issue.tenant = context.get("tenant", "default")

    attachments = issue_tracker.get_attachments(issue.id)
    issue.attachments = attachments

    verdict = llm.analyze(
        f"Analyze this bug report for auto-fix eligibility.\n"
        f"Title: {issue.title}\nDescription: {issue.description}\n\n"
        "Reply with one word: FIXABLE or VAGUE."
    ).strip().upper()

    if "VAGUE" in verdict:
        issue_tracker.post_comment(
            issue.id,
            "This issue needs more detail for automated fixing. "
            "Please include: steps to reproduce, expected vs actual behavior, and relevant error logs.",
        )
        issue_tracker.update_status(issue.id, ZohoStatus.NEEDS_CLARIFICATION)
        raise IssueVagueError(f"Issue {issue.id} lacks sufficient detail")

    return {**context, "issue": issue}
