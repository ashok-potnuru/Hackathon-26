from core.observability.logger import get_logger

logger = get_logger(__name__)


async def run(context: dict) -> dict:
    issue = context["issue"]
    adapters = context["adapters"]
    settings = adapters.get("settings", {})

    title = issue.title
    description = issue.description
    repo = (issue.affected_repos or settings.get("default_repos") or [""])[0]
    base_branch = issue.target_branch or settings.get("default_branch", "master")
    vc_adapter = adapters["version_control"]

    logger.info(f"agent_runner: repo={repo} branch={base_branch} issue={issue.id}")

    from scripts.agents_pipeline import run as run_agents
    result = run_agents(
        title=title,
        description=description,
        github_repo=repo,
        base_branch=base_branch,
        vc_adapter=vc_adapter,
        create_pr=True,
    )

    return {
        **context,
        "fix": result["coder_result"],
        "pr_url": result["pr_url"],
        "agent_result": result,
    }
