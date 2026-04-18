import os, sys, re, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts._llm_loader import load_llm
from core.agents.planner_agent import PlannerAgent
from core.agents.explorer_agent import ExplorerAgent
from core.agents.coder_agent import CoderAgent
from core.agents.reviewer_agent import ReviewerAgent
from core.utils.graph_navigator import get_navigator
from adapters.version_control.github import GitHubAdapter
from core.models.pr import PRModel


def run(title: str, description: str, github_repo: str = "", base_branch: str = "master",
        vc_adapter=None, create_pr: bool = True, repo_type: str = "api",
        cross_repo_context: str = "") -> dict:
    """
    Run the full multi-agent chain driven by job data from the Zoho webhook.

    Args:
        title:       Item name from Zoho
        description: Item description from Zoho — used as the LLM prompt
        github_repo: e.g. "org/repo" — derived from env (API_REPO/CMS_REPO) if empty
        base_branch: PR target branch
        vc_adapter:  version_control adapter to fetch files via GitHub API
        create_pr:   whether to open a GitHub PR at the end
        repo_type:          "api" (Node.js) or "cms" (PHP/Laravel)
        cross_repo_context: summary of what the other repo's pipeline already planned,
                            passed to PlannerAgent so field names stay consistent

    Returns:
        dict with plan, explorer_result, coder_result, reviewer_result, pr_url
    """
    if not github_repo:
        env_key = "API_REPO" if repo_type == "api" else "CMS_REPO"
        github_repo = os.getenv(env_key, "")

    llm = load_llm()

    # ── STEP 1: PlannerAgent ─────────────────────────────────────────────────
    nav = get_navigator(repo_type)
    planner = PlannerAgent(llm, nav)
    plan = planner.plan(title, description, cross_repo_context=cross_repo_context)

    if not plan.target_files:
        plan.target_files = ["services/placeholder.js"]

    # ── STEP 2: ExplorerAgent ────────────────────────────────────────────────
    code_sections = {}
    for path in plan.target_files[:3]:
        if vc_adapter:
            try:
                code_sections[path] = vc_adapter.get_file(github_repo, path, base_branch)
            except Exception as e:
                code_sections[path] = f"// file not found: {path} ({e})"
        else:
            codebase_root = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "..", "hackathon_wlb_api",
            )
            try:
                with open(os.path.join(codebase_root, path)) as f:
                    code_sections[path] = f.read()
            except FileNotFoundError:
                code_sections[path] = f"// file not found locally: {path}"

    explorer = ExplorerAgent(llm)
    explorer_result = explorer.explore(title, description, code_sections)

    # ── STEP 3: CoderAgent ───────────────────────────────────────────────────
    coder_input = {
        **explorer_result.must_change_files,
        **{f"[CONTEXT] {p}": v for p, v in explorer_result.context_files.items()},
    }
    coder = CoderAgent(llm)
    coder_result = coder.generate(
        title=title,
        description=description,
        code_context=coder_input,
        base_files=code_sections,
        repo_type=repo_type,
    )

    # ── STEP 4: ReviewerAgent ────────────────────────────────────────────────
    reviewer = ReviewerAgent(llm)
    reviewer_result = reviewer.review(
        description=description,
        original_code=explorer_result.must_change_files,
        proposed_changes=coder_result.file_contents,
    )

    # ── STEP 5: GitHub PR ────────────────────────────────────────────────────
    pr_url = None
    if create_pr and coder_result.file_contents:
        try:
            gh = vc_adapter or GitHubAdapter()
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower())[:40].strip("-")
            branch_name = f"autofix/{slug}-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
            gh.create_branch(github_repo, branch_name, base_branch)
            gh.commit_changes(
                repo=github_repo,
                branch=branch_name,
                files=coder_result.file_contents,
                message=f"autofix: {title}",
            )

            checks_md = ""
            if reviewer_result.checks:
                rows = "\n".join(f"| {k} | {v} |" for k, v in reviewer_result.checks.items())
                checks_md = f"\n\n## AI Reviewer Checks\n| Check | Result |\n|---|---|\n{rows}"

            pr_body = (
                f"## Summary\n{coder_result.reasoning}\n\n"
                f"## Files Changed\n" +
                "\n".join(f"- `{f}`" for f in coder_result.file_contents) +
                f"\n\n## AI Review Verdict: {reviewer_result.verdict}\n"
                f"{reviewer_result.feedback or '(no feedback)'}"
                f"{checks_md}\n\n"
                f"**Confidence:** {coder_result.confidence:.0%}  \n"
                f"> Auto-generated by multi-agent pipeline. Requires human review before merge."
            )

            pr = gh.create_pr(PRModel(
                title=f"[AutoFix] {title}",
                body=pr_body,
                branch_name=branch_name,
                base_branch=base_branch,
                repo=github_repo,
                reviewer="",
                zoho_issue_id="",
                draft=True,
            ))
            pr_url = pr.url
        except Exception as e:
            print(f"PR creation failed: {e}")

    return {
        "plan": plan,
        "explorer_result": explorer_result,
        "coder_result": coder_result,
        "reviewer_result": reviewer_result,
        "pr_url": pr_url,
    }
