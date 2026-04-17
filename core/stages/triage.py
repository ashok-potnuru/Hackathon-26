from core.constants import IssuePriority, TargetBranch, ZohoStatus
from core.exceptions import NotFixableError


async def run(context: dict) -> dict:
    issue = context["issue"]
    adapters = context["adapters"]
    llm = adapters["llm"]
    issue_tracker = adapters["issue_tracker"]
    work_type = context.get("work_type", "bugfix")

    if work_type == "feature":
        prompt = (
            f"PRD/Task:\nTitle: {issue.title}\nContent:\n{issue.description}\n\n"
            "Can this feature be implemented automatically by generating code changes from the PRD? "
            "Also list affected repository names (owner/repo format, comma-separated). "
            "Format your response exactly as:\nIMPLEMENTABLE: YES/NO\nREPOS: repo1,repo2"
        )
        no_keyword = "IMPLEMENTABLE: NO"
        yes_keyword = "IMPLEMENTABLE:"
        not_fixable_comment = "This PRD requires manual implementation and cannot be auto-generated."
    else:
        prompt = (
            f"Bug report:\nTitle: {issue.title}\nDescription: {issue.description}\n\n"
            "Is this bug fixable by automated code changes? "
            "Also list affected repository names (owner/repo format, comma-separated). "
            "Format your response exactly as:\nFIXABLE: YES/NO\nREPOS: repo1,repo2"
        )
        no_keyword = "FIXABLE: NO"
        yes_keyword = "FIXABLE:"
        not_fixable_comment = "This issue requires manual investigation and cannot be resolved automatically."

    result = llm.analyze(prompt)
    upper = result.upper()

    if no_keyword in upper or (yes_keyword in upper and "YES" not in upper):
        issue_tracker.post_comment(issue.id, not_fixable_comment)
        issue_tracker.update_status(issue.id, ZohoStatus.NEEDS_MANUAL_REVIEW)
        raise NotFixableError(f"Issue {issue.id} is not auto-{'implementable' if work_type == 'feature' else 'fixable'}")

    repos: list = []
    for line in result.splitlines():
        if line.upper().startswith("REPOS:"):
            repos = [r.strip() for r in line.split(":", 1)[1].split(",") if r.strip()]
            break

    issue.affected_repos = repos or context.get("affected_repos", [])

    if work_type == "feature":
        issue.target_branch = TargetBranch.NORMAL
    else:
        issue.target_branch = TargetBranch.CRITICAL if issue.priority == IssuePriority.CRITICAL else TargetBranch.NORMAL

    issue_tracker.update_status(issue.id, ZohoStatus.IN_PROGRESS)
    return {**context, "issue": issue}
