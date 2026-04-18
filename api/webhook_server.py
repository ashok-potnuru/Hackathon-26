import logging
import os
import re

from dotenv import load_dotenv
load_dotenv()

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from api.middleware import verify_zoho_webhook
from adapters.issue_tracker.zoho_sprints import encode_item_id
from core.queue.producer import enqueue_job

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="AutoFix AI")

_ZOHO_ITEM_EVENTS = {
    "Item_CREATE", "Item Create", "Item_ADDED",
    "Item_UPDATE", "Item Update", "Item_MODIFIED",
}


@app.get("/")
@app.get("/webhook/zoho")
async def zoho_verify():
    return {"status": "ok"}


@app.post("/")
@app.post("/webhook/zoho")
async def zoho_webhook(request: Request, background_tasks: BackgroundTasks):
    await verify_zoho_webhook(request, os.environ.get("ZOHO_SPRINTS_WEBHOOK_TOKEN", ""))

    content_type = request.headers.get("content-type", "")
    if "form" in content_type:
        body = dict(await request.form())
    else:
        body = await request.json()

    logger.info(f"ZOHO WEBHOOK: {body}")

    event_type = str(body.get("triggerEvent") or body.get("zsaction") or "").strip()
    if event_type not in _ZOHO_ITEM_EVENTS:
        return {"status": "ignored", "reason": f"unhandled event_type: {event_type}"}

    team_id = str(body.get("zoid") or os.environ.get("ZOHO_SPRINTS_TEAM_ID", ""))
    item_id = str(body.get("itemId") or body.get("item_id") or "")
    if not item_id or not item_id.strip().lstrip("-").isdigit():
        raise HTTPException(status_code=400, detail=f"Missing item ID — keys: {list(body.keys())}")

    data_str = str(body.get("data") or "")
    m = re.search(r'"ItemName"\s*:\s*([^\r\n]+)', data_str)
    title = m.group(1).strip().rstrip(",").strip() if m else ""
    m = re.search(r'"ItemDescription"\s*:\s*([^\r\n]+)', data_str)
    description = m.group(1).strip() if m else ""

    composite_id = encode_item_id(team_id, item_id)

    background_tasks.add_task(enqueue_job, {
        "source": "zoho_sprints",
        "issue_id": composite_id,
        "title": title,
        "description": description,
        "projectId": str(body.get("projectId", "")),
        "sprintId": str(body.get("sprintId", "")),
        "event_type": event_type,
        "tenant": team_id,
    })
    return {"status": "accepted", "issue_id": composite_id}
