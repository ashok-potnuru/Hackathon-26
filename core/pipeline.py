import time

from core.constants import PipelineStage
from core.exceptions import DuplicatePRError, FixGenerationError, IssueVagueError, NotFixableError, PRTooLargeError
from core.observability.logger import get_logger, log_stage_event
from core.observability.metrics import metrics
from core.observability.tracer import tracer
from core.stages import ci_handler, closure, fix_generator, intake, pr_creator, research, reviewer_handler, triage

logger = get_logger(__name__)

_MAIN_STAGES = [
    (PipelineStage.INTAKE, intake.run),
    (PipelineStage.TRIAGE, triage.run),
    (PipelineStage.RESEARCH, research.run),
    (PipelineStage.FIX_GENERATION, fix_generator.run),
    (PipelineStage.PR_CREATION, pr_creator.run),
]

_EVENT_STAGES = {
    "github_review": (PipelineStage.DEVELOPER_REVIEW, reviewer_handler.run),
    "github_ci": (PipelineStage.CI, ci_handler.run),
    "github_merge": (PipelineStage.CLOSURE, closure.run),
}

_SOFT_ERRORS = (IssueVagueError, NotFixableError, PRTooLargeError, DuplicatePRError)


async def run_pipeline(payload: dict, adapters: dict) -> None:
    issue_id = str(payload.get("issue_id", "unknown"))
    tenant = payload.get("tenant", "default")
    source = payload.get("source", "zoho")
    trace_id = tracer.start_trace(issue_id)

    context = {"payload": payload, "adapters": adapters, "tenant": tenant, "trace_id": trace_id}

    if source in _EVENT_STAGES:
        stage_name, stage_fn = _EVENT_STAGES[source]
        await _run_stage(stage_name, stage_fn, context, issue_id, tenant)
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
        return None
    except Exception as e:
        metrics.record_stage_end(stage_name, start, success=False)
        tracer.end_span(span, "error")
        log_stage_event(logger, "stage_failed", stage_name, issue_id, tenant, error=str(e))
        raise
