import os

import boto3

from core.observability.logger import get_logger

logger = get_logger(__name__)


async def run(context: dict) -> dict:
    payload = context["payload"]
    issue_id = str(payload.get("issue_id", "unknown"))
    description = str(payload.get("description", ""))
    pipeline_name = str(payload.get("pipeline_name") or os.environ.get("AWS_CODEPIPELINE_NAME", ""))

    if not pipeline_name:
        raise RuntimeError("AWS_CODEPIPELINE_NAME not set — cannot trigger deployment")

    client = boto3.client("codepipeline", region_name=os.environ.get("AWS_REGION", "us-east-1"))

    branch = str(payload.get("branch") or "").strip()
    if branch:
        r = client.get_pipeline(name=pipeline_name)
        pipeline_cfg = r["pipeline"]
        pipeline_cfg.pop("version", None)
        for stage in pipeline_cfg.get("stages", []):
            for action in stage.get("actions", []):
                if "BranchName" in action.get("configuration", {}):
                    action["configuration"]["BranchName"] = branch
        client.update_pipeline(pipeline=pipeline_cfg)
        logger.info(f"deploy: branch switched to {branch}")

    resp = client.start_pipeline_execution(
        name=pipeline_name,
        variables=[
            {"name": "issue_id", "value": issue_id},
            {"name": "description", "value": description[:1000]},
        ],
    )
    execution_id = resp["pipelineExecutionId"]
    logger.info(f"deploy: pipeline={pipeline_name} executionId={execution_id}")

    try:
        context["adapters"]["notification"].send_success(
            f"Deployment started for [{issue_id}] — pipeline: {pipeline_name} | executionId: {execution_id}"
        )
    except Exception:
        pass

    return {**context, "execution_id": execution_id}
