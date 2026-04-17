import json

from core.constants import ZohoStatus


async def run(context: dict) -> dict:
    payload = context["payload"]
    adapters = context["adapters"]
    issue = context.get("issue")
    fix = context.get("fix")
    pr = context.get("pr")

    if not pr or not issue:
        return context

    comment = (
        payload.get("review", {}).get("body", "")
        or payload.get("comment", {}).get("body", "")
    )
    if not comment:
        return context

    llm = adapters["llm"]
    vc = adapters["version_control"]
    issue_tracker = adapters["issue_tracker"]
    notification = adapters["notification"]

    raw = llm.generate_fix({
        "title": issue.title,
        "description": (
            f"Developer review feedback:\n{comment}\n\n"
            f"Original fix reasoning:\n{fix.reasoning if fix else ''}"
        ),
        "code_context": fix.diff if fix else "",
        "similar_fixes": "",
    })

    try:
        data = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
        if data.get("files"):
            vc.commit_changes(
                pr.repo, pr.branch_name, data["files"],
                f"fix: address review feedback for issue {issue.id}",
            )
    except (ValueError, json.JSONDecodeError, Exception):
        pass

    issue_tracker.update_status(issue.id, ZohoStatus.UNDER_REVIEW)
    notification.send_message("", f"Review feedback addressed on PR {pr.url}")

    return context
