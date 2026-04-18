from core.agents.planner_agent import PlannerAgent
from core.constants import MAX_FILES_FOR_AUTO_FIX
from core.exceptions import PRTooLargeError
from core.utils.graph_navigator import get_navigator


async def run(context: dict) -> dict:
    issue = context["issue"]
    adapters = context["adapters"]
    llm = adapters["llm"]
    vc = adapters["version_control"]
    vs = adapters["vector_store"]

    similar = vs.search_similar(f"{issue.title} {issue.description}", top_k=3)
    similar_text = "\n".join(f"Issue: {h['issue']}\nFix: {h['fix']}" for h in similar)

    code_parts: list = []
    all_relevant: list = []

    # Graph-based file discovery: reads local graph.json (committed to repo)
    nav = get_navigator()
    planner = PlannerAgent(llm, nav)
    plan = planner.plan(issue.title, issue.description)

    if plan.target_files:
        repo = issue.affected_repos[0] if issue.affected_repos else ""
        all_relevant = plan.target_files[:MAX_FILES_FOR_AUTO_FIX]
        for path in all_relevant:
            try:
                content = vc.get_file(repo, path, issue.target_branch)
                code_parts.append(f"# {repo}/{path}\n{content}")
            except Exception:
                pass
        return {**context, "research": {
            "code_context": "\n\n".join(code_parts),
            "similar_fixes": similar_text,
            "relevant_files": all_relevant,
            "plan": plan,
        }}

    # Fallback: original LLM file-listing path (unchanged)
    for repo in issue.affected_repos[:2]:
        try:
            files = vc.list_files(repo, issue.target_branch)
        except Exception:
            continue

        relevant_str = llm.analyze(
            f"Bug: {issue.title}\nDescription: {issue.description}\n\n"
            f"Repository files: {', '.join(files[:150])}\n\n"
            f"List up to {MAX_FILES_FOR_AUTO_FIX} file paths most likely containing the bug. "
            "One path per line. No explanations."
        )
        relevant = [
            ln.strip() for ln in relevant_str.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ][:MAX_FILES_FOR_AUTO_FIX]
        all_relevant.extend(relevant)

        if len(all_relevant) > MAX_FILES_FOR_AUTO_FIX:
            raise PRTooLargeError(f"Too many files affected: {len(all_relevant)}")

        for path in relevant:
            try:
                content = vc.get_file(repo, path, issue.target_branch)
                code_parts.append(f"# {repo}/{path}\n{content}")
            except Exception:
                pass

    return {**context, "research": {
        "code_context": "\n\n".join(code_parts),
        "similar_fixes": similar_text,
        "relevant_files": all_relevant,
    }}
