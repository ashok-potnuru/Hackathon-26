import logging
import os
import re

from dotenv import load_dotenv
load_dotenv()

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from api.middleware import verify_zoho_webhook
from adapters.issue_tracker.zoho_sprints import encode_item_id
from adapters.notification.teams import notify_deployment_status
from core.queue.producer import enqueue_job

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="AutoFix AI")

_processed_approvals: set[str] = set()


@app.post("/api/approvals")
async def handle_approval(request: Request, background_tasks: BackgroundTasks):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    action = body.get("action")
    if action not in ("approved", "denied"):
        raise HTTPException(status_code=400, detail=f"Invalid action: {action!r}")

    issue_id = str(body.get("issue_id", "unknown"))
    branch = str(body.get("branch", ""))
    title = str(body.get("title", ""))
    pr_url = str(body.get("pr_url", ""))

    logger.info(f"APPROVAL: action={action} issue_id={issue_id} branch={branch}")

    if action == "approved":
        background_tasks.add_task(enqueue_job, {
            "source": "deploy",
            "issue_id": issue_id,
            "branch": branch,
            "description": title,
            "pr_url": pr_url,
        })
        return {"status": "accepted", "action": action, "issue_id": issue_id}

    return {"status": "ok", "action": action, "issue_id": issue_id}

def _safe_notify(issue_id: str, title: str, pr_url: str, action: str) -> None:
    try:
        notify_deployment_status(issue_id, title, pr_url, action)
    except Exception as e:
        logger.warning(f"Teams status notification failed: {e}")


def _approval_html(action: str, issue_id: str, pr_url: str, title: str) -> str:
    approved = action == "approved"
    color = "#00C853" if approved else "#FF5252"
    icon = "✅" if approved else "❌"
    label = "Approved — deployment triggered" if approved else "Rejected"
    pr_link = f'<p><a href="{pr_url}" target="_blank">View PR</a></p>' if pr_url else ""
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>AutoFix {label}</title>
<style>body{{font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#f5f5f5}}
.card{{background:#fff;border-radius:8px;padding:40px;box-shadow:0 2px 8px rgba(0,0,0,.15);text-align:center;max-width:480px}}
h2{{color:{color}}}p{{color:#555}}</style></head>
<body><div class="card"><h2>{icon} {label}</h2>
<p><strong>{title or issue_id}</strong></p>{pr_link}
<p style="font-size:12px;color:#999">Issue: {issue_id}</p></div></body></html>"""


@app.get("/api/approvals/confirm", response_class=HTMLResponse)
async def confirm_approval(
    request: Request,
    background_tasks: BackgroundTasks,
    action: str = "",
    issue_id: str = "",
    branch: str = "",
    title: str = "",
    pr_url: str = "",
):
    if action not in ("approved", "denied"):
        raise HTTPException(status_code=400, detail="Invalid action")

    logger.info(f"APPROVAL (browser): action={action} issue_id={issue_id} branch={branch}")

    dedup_key = f"{issue_id}:{action}"
    if dedup_key in _processed_approvals:
        logger.info(f"Duplicate approval ignored: {dedup_key}")
        return HTMLResponse(_approval_html(action, issue_id, pr_url, title))
    _processed_approvals.add(dedup_key)

    if action == "approved":
        background_tasks.add_task(enqueue_job, {
            "source": "deploy",
            "issue_id": issue_id,
            "branch": branch,
            "description": title,
            "pr_url": pr_url,
        })

    background_tasks.add_task(_safe_notify, issue_id, title, pr_url, action)

    return HTMLResponse(_approval_html(action, issue_id, pr_url, title))


def _extract_item_fields(body: dict) -> tuple[str, str]:
    """Extract title and description from a Zoho webhook body.

    Zoho sends 'data' as a pseudo-JSON string where values may be unquoted,
    e.g.: "ItemName" : Some text here,
    We handle both quoted and unquoted values.
    """
    import json as _json
    data_raw = body.get("data") or ""
    data: dict = {}
    if isinstance(data_raw, dict):
        data = data_raw
    elif isinstance(data_raw, str) and data_raw.strip().startswith("{"):
        try:
            data = _json.loads(data_raw)
        except Exception:
            pass

    title = ""
    for key in ("ItemName", "itemName", "name", "title", "item_name"):
        val = data.get(key) or body.get(key, "")
        if val and str(val).strip():
            title = str(val).strip()
            break

    description = ""
    for key in ("ItemDescription", "itemDescription", "description", "desc"):
        val = data.get(key) or body.get(key, "")
        if val and str(val).strip():
            description = str(val).strip()
            break

    # Zoho often sends unquoted values; fall back to flexible regex
    if not title and isinstance(data_raw, str):
        # Title is always a single line, ends at comma or newline
        m = re.search(r'"ItemName"\s*:\s*"?([^"\n,}]+)', data_raw)
        if m:
            title = m.group(1).strip()

    if not description and isinstance(data_raw, str):
        # Description is HTML spanning multiple lines, ends just before closing \n}
        m = re.search(r'"ItemDescription"\s*:\s*([\s\S]*?)\s*\n\}', data_raw)
        if m:
            description = m.group(1).strip().strip('"')

    return title, description


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

    title, description = _extract_item_fields(body)

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
