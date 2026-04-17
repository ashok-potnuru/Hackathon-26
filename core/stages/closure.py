from core.constants import ZohoStatus


async def run(context: dict) -> dict:
    adapters = context["adapters"]
    issue = context.get("issue")
    fix = context.get("fix")
    pr = context.get("pr")

    issue_tracker = adapters["issue_tracker"]
    vs = adapters["vector_store"]
    notification = adapters["notification"]

    if issue:
        issue_tracker.update_status(issue.id, ZohoStatus.FIXED)
        issue_tracker.post_comment(
            issue.id,
            f"Issue resolved. Auto-fix merged via {pr.url if pr else 'PR'}.",
        )

    if issue and fix:
        vs.store_fix(
            issue_id=issue.id,
            issue_text=f"{issue.title} {issue.description}",
            fix_text=fix.reasoning,
        )

    if issue:
        notification.send_feedback_prompt("", issue.id)
        notification.send_message(
            "", f"Issue {issue.id} closed. Fix merged in {pr.url if pr else 'unknown PR'}."
        )

    return context
