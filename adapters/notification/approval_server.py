from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
import uvicorn
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Teams Deployment Approval Receiver")

decisions: list[dict] = []


# ──────────────────────────────────────────────
# Receive approval from Teams button click
# ──────────────────────────────────────────────

@app.post("/api/approvals")
async def receive_approval(request: Request):

    # ── 1. Parse body ──────────────────────────
    raw_body = await request.body()
    logger.info("─" * 50)
    logger.info(f"📨  Incoming: {raw_body.decode('utf-8', errors='replace')}")

    try:
        body = await request.json()
    except Exception as e:
        logger.warning(f"JSON parse error: {e}")
        body = {}

    # ── 2. Extract all deployment fields ───────
    action       = body.get("action")
    request_id   = body.get("request_id")
    app_type     = body.get("app_type")      # cms | api | frontend
    branch       = body.get("branch")
    version      = body.get("version")
    environment  = body.get("environment")
    service      = body.get("service")
    region       = body.get("region")
    triggered_by = body.get("triggered_by")
    commit_id    = body.get("commit_id")
    description  = body.get("description")

    # ── 3. Log everything clearly ──────────────
    logger.info(f"    action       = {action}")
    logger.info(f"    request_id   = {request_id}")
    logger.info(f"    app_type     = {app_type}")
    logger.info(f"    branch       = {branch}")
    logger.info(f"    version      = {version}")
    logger.info(f"    environment  = {environment}")
    logger.info(f"    service      = {service}")
    logger.info(f"    region       = {region}")
    logger.info(f"    triggered_by = {triggered_by}")
    logger.info(f"    commit_id    = {commit_id}")
    logger.info(f"    description  = {description}")
    logger.info("─" * 50)

    # ── 4. Validate ────────────────────────────
    if not action or action not in ("approved", "denied"):
        return JSONResponse({"error": f"Invalid action: {action!r}"}, status_code=400)
    if not request_id:
        return JSONResponse({"error": "Missing request_id"}, status_code=400)

    # ── 5. Store record ────────────────────────
    record = {
        "request_id":   request_id,
        "action":       action,
        "app_type":     app_type,
        "branch":       branch,
        "version":      version,
        "environment":  environment,
        "service":      service,
        "region":       region,
        "triggered_by": triggered_by,
        "commit_id":    commit_id,
        "description":  description,
        "timestamp":    datetime.now(timezone.utc).isoformat(),
    }
    decisions.append(record)

    # ── 6. Trigger deployment logic ────────────
    if action == "approved":
        logger.info(f"✅  APPROVED — triggering deployment")
        logger.info(f"    service={service}  branch={branch}  env={environment}  region={region}")
        _trigger_deployment(record)
    else:
        logger.info(f"❌  DENIED — deployment cancelled by {triggered_by}")
        _cancel_deployment(record)

    return JSONResponse({"status": "ok", "recorded": record})


# ──────────────────────────────────────────────
# Deployment handlers — plug your AWS logic here
# ──────────────────────────────────────────────

def _trigger_deployment(record: dict):
    """
    Called when Approve is clicked.
    Use record fields to deploy to AWS.

    Example with boto3:
        import boto3
        client = boto3.client("codedeploy", region_name=record["region"])
        client.create_deployment(
            applicationName=record["service"],
            deploymentGroupName=record["environment"],
            revision={...},
        )
    """
    logger.info(f"🚀  Deploying {record['service']} v{record['version']}")
    logger.info(f"    Branch : {record['branch']}")
    logger.info(f"    Env    : {record['environment']}")
    logger.info(f"    Region : {record['region']}")
    logger.info(f"    Type   : {record['app_type']}")
    # TODO: add your AWS deploy call here


def _cancel_deployment(record: dict):
    """
    Called when Deny is clicked.
    """
    logger.info(f"🛑  Deployment cancelled: {record['service']} v{record['version']}")
    # TODO: notify team, close ticket, etc.


# ──────────────────────────────────────────────
# Read decisions
# ──────────────────────────────────────────────

@app.get("/api/approvals")
async def get_approvals(request: Request):
    action     = request.query_params.get("action")
    request_id = request.query_params.get("request_id")
    if action and request_id:
        return await receive_approval(request)
    return {"total": len(decisions), "decisions": decisions}


@app.get("/api/approvals/{request_id}")
def get_decision(request_id: str):
    matches = [d for d in decisions if d["request_id"] == request_id]
    if not matches:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return {"request_id": request_id, "decisions": matches}


@app.get("/health")
def health():
    return {"status": "ok", "decisions_count": len(decisions)}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)