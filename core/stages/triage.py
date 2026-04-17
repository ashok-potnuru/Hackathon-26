from core.constants import IssuePriority, TargetBranch, ZohoStatus
from core.exceptions import NotFixableError


async def run(context: dict) -> dict:
    issue = context["issue"]
    adapters = context["adapters"]
    llm = adapters["llm"]
    issue_tracker = adapters["issue_tracker"]

    result = llm.analyze(
        f"Bug report:\nTitle: {issue.title}\nDescription: {issue.description}\n\n"
        "Is this bug fixable by automated code changes? "
        "Also list affected repository names (owner/repo format, comma-separated). "
        "Format your response exactly as:\nFIXABLE: YES/NO\nREPOS: repo1,repo2"
    )

    upper = result.upper()
    if "FIXABLE: NO" in upper or ("FIXABLE:" in upper and "YES" not in upper):
        issue_tracker.post_comment(
            issue.id,
            "This issue requires manual investigation and cannot be resolved automatically.",
        )
        issue_tracker.update_status(issue.id, ZohoStatus.NEEDS_MANUAL_REVIEW)
        raise NotFixableError(f"Issue {issue.id} is not auto-fixable")

    repos: list = []
    for line in result.splitlines():
        if line.upper().startswith("REPOS:"):
            repos = [r.strip() for r in line.split(":", 1)[1].split(",") if r.strip()]
            break

    issue.affected_repos = repos or context.get("affected_repos", [])
    issue.target_branch = TargetBranch.CRITICAL if issue.priority == IssuePriority.CRITICAL else TargetBranch.NORMAL

    issue_tracker.update_status(issue.id, ZohoStatus.IN_PROGRESS)
    return {**context, "issue": issue}
