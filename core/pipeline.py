import datetime
import re
import time

from core.constants import PipelineStage
from core.exceptions import IssueVagueError, NotFixableError
from core.observability.logger import get_logger, log_stage_event
from core.observability.metrics import metrics
from core.observability.tracer import tracer
from core.stages import agent_runner, deployer, intake

logger = get_logger(__name__)


def _create_fallback_pr(context: dict, error: Exception) -> str | None:
    """Create a placeholder PR when the agent pipeline fails (e.g. LLM quota exceeded)."""
    try:
        adapters = context["adapters"]
        issue = context.get("issue")
        if not issue:
            return None

        settings = adapters.get("settings", {})
        base_branch = settings.get("default_branch", "SIT")
        repos = settings.get("default_repos", {})
        repo = repos.get("api", "")
        if not repo:
            return None

        gh = adapters["version_control"]
        slug = re.sub(r"[^a-z0-9]+", "-", issue.title.lower())[:40].strip("-")
        branch_name = f"autofix/pending/{slug}-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        file_path = f"autofix/pending/{issue.id.replace('|', '_')}.md"
        file_content = (
            f"# AutoFix Pending: {issue.title}\n\n"
            f"**Issue ID:** {issue.id}  \n"
            f"**Status:** Awaiting manual fix (automated pipeline failed)  \n"
            f"**Error:** {error}  \n\n"
            f"## Description\n\n{issue.description or '_(no description)_'}\n"
        )

        gh.create_branch(repo, branch_name, base_branch)
        gh.commit_changes(repo, branch_name, {file_path: file_content}, f"autofix(pending): {issue.title}")

        from core.models.pr import PRModel
        pr = gh.create_pr(PRModel(
            title=f"[AutoFix Pending] {issue.title}",
            body=(
                f"## Automated fix failed\n\n"
                f"The AutoFix pipeline could not generate a code fix for this issue.\n\n"
                f"**Reason:** `{error}`\n\n"
                f"Please review and fix manually.\n\n"
                f"---\n{issue.description or ''}"
            ),
            branch_name=branch_name,
            base_branch=base_branch,
            repo=repo,
            reviewer="",
            zoho_issue_id=issue.id,
            draft=True,
        ))
        logger.info(f"Fallback PR created: {pr.url}")
        return pr.url
    except Exception as fb_err:
        logger.warning(f"Fallback PR creation failed: {fb_err}")
        return None

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
        try:
            context = await _run_stage(stage_name, stage_fn, context, issue_id, tenant)
        except Exception as e:
            if stage_name == PipelineStage.FIX_GENERATION:
                logger.error(f"FIX_GENERATION failed — creating fallback PR: {e}")
                fallback_url = _create_fallback_pr(context, e)
                if fallback_url:
                    issue = context.get("issue")
                    issue_title = issue.title if issue else issue_id
                    settings = adapters.get("settings", {})
                    try:
                        adapters["notification"].notify_pr_raised(
                            issue_id=issue_id,
                            title=f"[Pending] {issue_title}",
                            pr_url=fallback_url,
                            branch="",
                            base_branch=settings.get("default_branch", "SIT"),
                        )
                    except Exception as ne:
                        logger.warning(f"Teams fallback notification failed: {ne}")
                else:
                    try:
                        adapters["notification"].send_alert(
                            "", f"AutoFix pipeline failed for [{issue_id}] and fallback PR could not be created: {e}"
                        )
                    except Exception:
                        pass
            return
        if context is None:
            return

    issue = context.get("issue")
    issue_title = issue.title if issue else issue_id
    pr_url = context.get("pr_url")

    if pr_url:
        try:
            settings = adapters.get("settings", {})
            base_branch = settings.get("default_branch", "SIT")
            branch = context.get("branch_name", "")
            # Also include second repo PR if multi-repo run
            meta_plan = context.get("meta_plan")
            extra_urls = []
            if meta_plan and len(meta_plan.repos) > 1:
                second = meta_plan.repos[1]
                second_url = context.get(f"{second}_pr_url")
                if second_url:
                    extra_urls.append((second, second_url))
            adapters["notification"].notify_pr_raised(
                issue_id=issue_id,
                title=issue_title,
                pr_url=pr_url,
                branch=branch,
                base_branch=base_branch,
                extra_pr_urls=extra_urls,
            )
        except Exception as e:
            logger.warning(f"Teams PR notification failed: {e}")
    else:
        try:
            adapters["notification"].send_alert(
                "", f"AutoFix completed for [{issue_id}] but no code changes were generated: {issue_title}"
            )
        except Exception:
            pass


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
