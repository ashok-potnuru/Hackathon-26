import os

import requests

from core.constants import ZohoStatus


async def run(context: dict) -> dict:
    payload = context["payload"]
    adapters = context["adapters"]
    issue = context.get("issue")
    pr = context.get("pr")

    llm = adapters["llm"]
    notification = adapters["notification"]

    ci_status = payload.get("state") or payload.get("conclusion") or ""
    ci_output = payload.get("output", {}).get("text", "") or payload.get("description", "")

    if ci_status in ("failure", "error"):
        diagnosis = llm.analyze(
            f"CI failed with this output:\n{ci_output}\n\n"
            "Diagnose the failure and suggest a fix in 2-3 sentences."
        )

        if pr:
            try:
                requests.post(
                    f"https://api.github.com/repos/{pr.repo}/issues/{pr.number}/comments",
                    headers={"Authorization": f"Bearer {os.environ.get('GITHUB_TOKEN', '')}",
                             "Accept": "application/vnd.github+json"},
                    json={"body": f"**CI Failure Diagnosis:**\n{diagnosis}"},
                )
            except Exception:
                pass

        notification.send_alert("", f"CI failed on PR {pr.url if pr else 'unknown'}: {diagnosis[:200]}")

        if issue:
            adapters["issue_tracker"].update_status(issue.id, ZohoStatus.IN_PROGRESS)

    elif ci_status == "success":
        notification.send_message("", f"CI passed on PR {pr.url if pr else 'unknown'}")
        if issue:
            adapters["issue_tracker"].update_status(issue.id, ZohoStatus.VALIDATING)

    return context
