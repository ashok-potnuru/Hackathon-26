import time

from core.constants import PipelineStage
from core.exceptions import IssueVagueError, NotFixableError
from core.observability.logger import get_logger, log_stage_event
from core.observability.metrics import metrics
from core.observability.tracer import tracer
from core.stages import agent_runner, deployer, intake

logger = get_logger(__name__)

_MAIN_STAGES = [
    (PipelineStage.INTAKE, intake.run),
    (PipelineStage.FIX_GENERATION, agent_runner.run),
]

_SOFT_ERRORS = (IssueVagueError, NotFixableError)


async def run_pipeline(payload: dict, adapters: dict) -> None:
    issue_id = str(payload.get("issue_id", "unknown"))
    tenant = payload.get("tenant", "default")
    source = payload.get("source", "zoho_sprints")
    trace_id = tracer.start_trace(issue_id)

    context = {"payload": payload, "adapters": adapters, "tenant": tenant, "trace_id": trace_id}

    if source == "deploy":
        await _run_stage(PipelineStage.DEPLOY, deployer.run, context, issue_id, tenant)
        return

    for stage_name, stage_fn in _MAIN_STAGES:
        context = await _run_stage(stage_name, stage_fn, context, issue_id, tenant)
        if context is None:
            return


async def _run_stage(stage_name: str, stage_fn, context: dict, issue_id: str, tenant: str) -> dict | None:
    span = tracer.start_span(context["trace_id"], stage_name, issue_id)
    start = time.time()
    log_stage_event(logger, "stage_started", stage_name, issue_id, tenant)

    try:
        result = await stage_fn(context)
        metrics.record_stage_end(stage_name, start, success=True)
        tracer.end_span(span, "ok")
        log_stage_event(logger, "stage_completed", stage_name, issue_id, tenant)
        return result
    except _SOFT_ERRORS as e:
        metrics.record_stage_end(stage_name, start, success=False)
        tracer.end_span(span, "skipped")
        log_stage_event(logger, "stage_failed", stage_name, issue_id, tenant, reason=str(e))
        try:
            context["adapters"]["notification"].send_alert(
                "", f"AutoFix stopped for [{issue_id}] at {stage_name}: {e}"
            )
        except Exception:
            pass
        return None
    except Exception as e:
        metrics.record_stage_end(stage_name, start, success=False)
        tracer.end_span(span, "error")
        log_stage_event(logger, "stage_failed", stage_name, issue_id, tenant, error=str(e))
        raise
