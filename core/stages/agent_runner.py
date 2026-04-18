from scripts._llm_loader import load_llm
from core.agents.meta_planner import MetaPlannerAgent
from core.observability.logger import get_logger

logger = get_logger(__name__)


def _repo_config(settings: dict, repo_type: str) -> str:
    """Resolve GitHub repo name from settings.default_repos dict."""
    default_repos = settings.get("default_repos", {})
    return default_repos.get(repo_type, "")


def _build_cross_repo_context(completed: dict[str, dict], shared_context: str) -> str:
    """Build a cross-repo context string from all already-completed pipelines."""
    if not completed:
        return ""
    parts = [f"Shared context:\n{shared_context}"] if shared_context else []
    for repo_type, result in completed.items():
        plan = result.get("plan")
        if plan:
            parts.append(
                f"{repo_type.upper()} repo already planned:\n"
                f"  Files targeted: {plan.target_files}\n"
                f"  Keywords used: {plan.keywords_extracted}\n"
                f"  Reasoning: {plan.reasoning}"
            )
    return "\n\n".join(parts)


async def run(context: dict) -> dict:
    issue = context["issue"]
    adapters = context["adapters"]
    settings = adapters.get("settings", {})

    title = issue.title
    description = issue.description
    base_branch = issue.target_branch or settings.get("default_branch", "master")
    vc_adapter = adapters["version_control"]

    # ── STEP 0: MetaPlannerAgent — deep per-repo planning ────────────────────
    llm = load_llm()
    meta_planner = MetaPlannerAgent(llm)
    meta_plan = meta_planner.plan(title, description)

    logger.info(
        f"agent_runner: meta_plan repos={meta_plan.repos} "
        f"reason={meta_plan.reasoning!r}"
    )

    from scripts.agents_pipeline import run as run_agents

    # ── STEP 1+: Run per-repo pipelines in order, passing context forward ────
    completed: dict[str, dict] = {}

    for repo_type in meta_plan.repos:
        repo_spec = meta_plan.spec_for(repo_type)
        cross_repo_ctx = _build_cross_repo_context(completed, meta_plan.shared_context)

        github_repo = (
            issue.affected_repos[0]
            if (repo_type == meta_plan.repos[0] and issue.affected_repos)
            else _repo_config(settings, repo_type)
        )

        logger.info(
            f"agent_runner: running {repo_type} pipeline "
            f"repo={github_repo} cross_repo={'yes' if cross_repo_ctx else 'no'}"
        )

        result = run_agents(
            title=title,
            description=repo_spec or description,
            github_repo=github_repo,
            base_branch=base_branch,
            vc_adapter=vc_adapter,
            create_pr=True,
            repo_type=repo_type,
            cross_repo_context=cross_repo_ctx,
            seed_keywords=meta_plan.keywords_for(repo_type),
        )
        completed[repo_type] = result

    # ── Return consolidated results ──────────────────────────────────────────
    if len(completed) == 1:
        repo_type = meta_plan.repos[0]
        result = completed[repo_type]
        return {
            **context,
            "fix": result["coder_result"],
            "pr_url": result["pr_url"],
            "branch_name": result.get("branch_name", ""),
            "agent_result": result,
            "meta_plan": meta_plan,
        }

    # Both repos ran
    first, second = meta_plan.repos[0], meta_plan.repos[1]
    return {
        **context,
        "fix": completed[first]["coder_result"],
        "pr_url": completed[first].get("pr_url"),
        "branch_name": completed[first].get("branch_name", ""),
        f"{second}_pr_url": completed[second].get("pr_url"),
        "agent_result": completed,
        "meta_plan": meta_plan,
    }
