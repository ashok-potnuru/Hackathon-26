import os

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from api.middleware import verify_github_signature, verify_zoho_webhook
from core.queue.producer import enqueue_job

app = FastAPI(title="AutoFix AI")


@app.post("/webhook/zoho/sprints")
async def zoho_sprints_webhook(request: Request, background_tasks: BackgroundTasks):
    await verify_zoho_webhook(request, os.environ.get("ZOHO_SPRINTS_WEBHOOK_TOKEN", ""))

    body = await request.json()
    team_id = os.environ.get("ZOHO_SPRINTS_TEAM_ID", "")
    item_id = str(body.get("itemId") or body.get("item_id") or body.get("id", ""))
    if not item_id:
        raise HTTPException(status_code=400, detail="Missing item ID in payload")

    from adapters.issue_tracker.zoho_sprints import encode_item_id
    composite_id = encode_item_id(team_id, item_id)

    background_tasks.add_task(enqueue_job, {
        "issue_id": composite_id,
        "source": "zoho_sprints",
        "payload": {**body, "source": "zoho_sprints"},
        "tenant": str(body.get("teamId", team_id)),
    })
    return {"status": "accepted", "issue_id": composite_id}


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
