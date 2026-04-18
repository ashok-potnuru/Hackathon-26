"""
Full multi-agent chain: Planner → Explorer → Coder → Reviewer

Each agent's output is passed directly into the next agent, exactly as the
real pipeline does it. No mocks, no placeholders — real LLM calls.

Run:
    source venv/bin/activate
    set -a && source .env && set +a
    python3 scripts/test_agents_live.py
"""
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

# ── Config ───────────────────────────────────────────────────────────────────
GITHUB_REPO  = "ashok-potnuru/hackathon_wlb_api"   # repo to push the PR to
BASE_BRANCH  = "SIT"                                # branch to target (PR base)
CREATE_PR    = True                                 # set False to skip PR creation
# ── Change these to test a different bug ─────────────────────────────────────
# ISSUE_TITLE       = "Add new two new keys in my auth paltform settings api response under region object these keys add in regions mode"
# ISSUE_DESCRIPTION = (
#     "keys names are max_video_height, max_video_bitrate_kbps"
#     "Error log shows: TypeError: Cannot read property 'amount' of undefined "
#     "inside the charge handler."
# )

ISSUE_TITLE       = "Add two new keys in Auth Platform Settings API response under region object and update Regions model"

ISSUE_DESCRIPTION = (
    "Add two new keys in the Platform Settings API response inside the region object. "
    "The key names are max_video_height and max_video_bitrate_kbps. "
    "These fields should be added to the Regions model and included in the API response. "
    "max_video_height represents the maximum allowed video height, and "
    "max_video_bitrate_kbps represents the optional maximum allowed video bitrate."
)
# ─────────────────────────────────────────────────────────────────────────────

def separator(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

llm = load_llm()
print(f"\nUsing: {type(llm).__name__}  model={llm._model}")
print(f"Issue: {ISSUE_TITLE}")

# ── STEP 1: PlannerAgent ─────────────────────────────────────────────────────
separator("STEP 1 — PlannerAgent")
print("  What it does: extracts keywords from issue, searches graph, returns files to fix\n")

nav     = get_navigator()
planner = PlannerAgent(llm, nav)
plan    = planner.plan(ISSUE_TITLE, ISSUE_DESCRIPTION)

print(f"  Keywords : {plan.keywords_extracted}")
print(f"  Type     : {plan.change_type}")
print(f"  Files ({len(plan.target_files)}):")
for f in plan.target_files:
    print(f"    - {f}")

if not plan.target_files:
    print("\n  [!] No files found in graph. Using fallback placeholder file for next steps.")
    plan.target_files = ["services/payments/charge.handler.js"]

# ── STEP 2: ExplorerAgent ────────────────────────────────────────────────────
separator("STEP 2 — ExplorerAgent")
print("  What it does: reads code, decides which files MUST change vs. context only\n")

# Read real file content from the local hackathon_wlb_api codebase
CODEBASE_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "hackathon_wlb_api")
code_sections = {}
for path in plan.target_files[:3]:   # limit to 3 files to save tokens
    full_path = os.path.join(CODEBASE_ROOT, path)
    try:
        with open(full_path) as f:
            code_sections[path] = f.read()
        print(f"  Loaded real file: {path} ({len(code_sections[path])} chars)")
    except FileNotFoundError:
        code_sections[path] = f"// file not found locally: {path}"
        print(f"  [!] Not found locally: {path}")

explorer        = ExplorerAgent(llm)
explorer_result = explorer.explore(ISSUE_TITLE, ISSUE_DESCRIPTION, code_sections)

print(f"  Summary: {explorer_result.summary}")
print(f"\n  Must change ({len(explorer_result.must_change_files)}):")
for f in explorer_result.must_change_files:
    print(f"    - {f}")
print(f"\n  Context only ({len(explorer_result.context_files)}):")
for f in explorer_result.context_files:
    print(f"    - {f}")

# ── STEP 3: CoderAgent ───────────────────────────────────────────────────────
separator("STEP 3 — CoderAgent")
print("  What it does: generates the actual code fix for the files that must change\n")

# Feed must_change files to coder; mark context files clearly
coder_input = {
    **explorer_result.must_change_files,
    **{f"[CONTEXT] {p}": v for p, v in explorer_result.context_files.items()},
}

coder        = CoderAgent(llm)
coder_result = coder.generate(
    title=ISSUE_TITLE,
    description=ISSUE_DESCRIPTION,
    code_context=coder_input,
    base_files=code_sections,   # full original files — edits applied against these
)

print(f"  Confidence : {coder_result.confidence:.2f}")
print(f"  Reasoning  : {coder_result.reasoning[:200]}")
print(f"\n  Surgical edits ({len(coder_result.edits)}):")
for i, edit in enumerate(coder_result.edits, 1):
    print(f"\n  Edit {i} → {edit.get('path')}")
    print(f"  {'─'*56}")
    print(f"  REMOVE:\n{edit.get('old_string', '')}")
    print(f"  ADD:\n{edit.get('new_string', '')}")
print(f"\n  Files touched: {list(coder_result.file_contents.keys())}")

# ── STEP 4: ReviewerAgent ────────────────────────────────────────────────────
separator("STEP 4 — ReviewerAgent")
print("  What it does: adversarial review — checks security, edge cases, correctness\n")

reviewer        = ReviewerAgent(llm)
reviewer_result = reviewer.review(
    description=ISSUE_DESCRIPTION,
    original_code=explorer_result.must_change_files,
    proposed_changes=coder_result.file_contents,
)

print(f"  Verdict     : {reviewer_result.verdict}")
print(f"  Approved    : {reviewer_result.approved}")
print(f"  Security OK : {reviewer_result.security_ok}")

if reviewer_result.checks:
    print("\n  Per-check results:")
    for check, outcome in reviewer_result.checks.items():
        print(f"    {check:<20} {outcome}")

if reviewer_result.feedback:
    print(f"\n  Feedback: {reviewer_result.feedback[:300]}")

# ── STEP 5: Create branch + commit + Draft PR on GitHub ──────────────────────
pr_url = None
if CREATE_PR and coder_result.file_contents:
    separator("STEP 5 — GitHub PR")
    print("  What it does: creates a branch, commits the fixes, opens a Draft PR\n")

    try:
        gh = GitHubAdapter()

        # Branch name: autofix/<slug>-<timestamp>
        slug = re.sub(r"[^a-z0-9]+", "-", ISSUE_TITLE.lower())[:40].strip("-")
        branch_name = f"autofix/{slug}-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        print(f"  Creating branch: {branch_name}")
        gh.create_branch(GITHUB_REPO, branch_name, BASE_BRANCH)

        print(f"  Committing {len(coder_result.file_contents)} file(s)...")
        gh.commit_changes(
            repo=GITHUB_REPO,
            branch=branch_name,
            files=coder_result.file_contents,
            message=f"autofix: {ISSUE_TITLE}",
        )

        # Build PR body with reviewer feedback included
        checks_md = ""
        if reviewer_result.checks:
            checks_md = "\n".join(
                f"| {k} | {v} |" for k, v in reviewer_result.checks.items()
            )
            checks_md = f"\n\n## AI Reviewer Checks\n| Check | Result |\n|---|---|\n{checks_md}"

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
            title=f"[AutoFix] {ISSUE_TITLE}",
            body=pr_body,
            branch_name=branch_name,
            base_branch=BASE_BRANCH,
            repo=GITHUB_REPO,
            reviewer="",
            zoho_issue_id="test",
            draft=True,
        ))
        pr_url = pr.url
        print(f"\n  Draft PR created: {pr_url}")

    except Exception as e:
        print(f"\n  [!] PR creation failed: {e}")

# ── FINAL SUMMARY ────────────────────────────────────────────────────────────
separator("FINAL SUMMARY")
print(f"  Planner   → {len(plan.target_files)} files identified")
print(f"  Explorer  → {len(explorer_result.must_change_files)} must change, {len(explorer_result.context_files)} context only")
print(f"  Coder     → {len(coder_result.file_contents)} files fixed  (confidence {coder_result.confidence:.2f})")
print(f"  Reviewer  → {reviewer_result.verdict}  ({'approved' if reviewer_result.approved else 'needs more work'})")
if pr_url:
    print(f"  PR        → {pr_url}")
print()
