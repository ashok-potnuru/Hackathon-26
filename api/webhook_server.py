import os

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from api.middleware import verify_github_signature, verify_zoho_webhook
from core.queue.producer import enqueue_job

app = FastAPI(title="AutoFix AI")


@app.post("/webhook/zoho")
async def zoho_webhook(request: Request, background_tasks: BackgroundTasks):
    await verify_zoho_webhook(request, os.environ.get("ZOHO_WEBHOOK_TOKEN", ""))

    body = await request.json()
    issue_id = body.get("ticketId") or body.get("id")
    if not issue_id:
        raise HTTPException(status_code=400, detail="Missing issue ID in payload")

    background_tasks.add_task(enqueue_job, {
        "issue_id": str(issue_id),
        "source": "zoho",
        "payload": body,
        "tenant": str(body.get("departmentId", "default")),
    })
    return {"status": "accepted", "issue_id": str(issue_id)}


@app.post("/webhook/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    if secret:
        await verify_github_signature(request, secret)

    body = await request.json()
    event = request.headers.get("X-GitHub-Event", "")

    if event in ("check_run", "check_suite", "status"):
        source = "github_ci"
    elif event == "pull_request_review":
        source = "github_review"
    elif event == "pull_request" and body.get("action") == "closed" and body.get("pull_request", {}).get("merged"):
        source = "github_merge"
    else:
        return {"status": "ignored"}

    background_tasks.add_task(enqueue_job, {"event": event, "source": source, "payload": body})
    return {"status": "accepted"}
