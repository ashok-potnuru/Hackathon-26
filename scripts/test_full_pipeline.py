"""
Full end-to-end multi-agent pipeline test.

Tests the complete flow for a real requirement:
  MetaPlannerAgent → per-repo PlannerAgent → GitHub fetch →
  ExplorerAgent → CoderAgent → ReviewerAgent → (optional) Draft PR

Each stage is logged verbosely so you can follow exactly what each agent
decides and why.

Run:
    source venv/bin/activate
    set -a && source .env && set +a
    python3 scripts/test_full_pipeline.py

Set CREATE_PR = True to also push branches and open Draft PRs.
Set TEST_SINGLE_REPO = "api" or "cms" to force a single-repo run.
"""

import os, sys, re, datetime, textwrap
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts._llm_loader import load_llm
from core.agents.meta_planner import MetaPlannerAgent
from core.agents.planner_agent import PlannerAgent
from core.agents.explorer_agent import ExplorerAgent
from core.agents.coder_agent import CoderAgent
from core.agents.reviewer_agent import ReviewerAgent
from core.utils.graph_navigator import get_navigator
from adapters.version_control.github import GitHubAdapter
from core.models.pr import PRModel

# ── Test config ──────────────────────────────────────────────────────────────
CREATE_PR        = True        # create a Draft PR after each repo's review
BASE_BRANCH_API  = "SIT"
BASE_BRANCH_CMS  = "SIT"
MAX_FILES        = 15          # gpt-4.5 1M context — fetch more files for better coverage
TEST_SINGLE_REPO = ""          # force "api" or "cms" to skip MetaPlanner routing

API_REPO = os.getenv("API_REPO", "ashok-potnuru/hackathon_wlb_api")
CMS_REPO = os.getenv("CMS_REPO", "ashok-potnuru/hackathon_wlb_cms")

REPO_MAP = {"api": API_REPO, "cms": CMS_REPO}
BRANCH_MAP = {"api": BASE_BRANCH_API, "cms": BASE_BRANCH_CMS}

# ── Requirement ───────────────────────────────────────────────────────────────
ISSUE_TITLE = "Zone-Level Playback Configuration"

ISSUE_DESCRIPTION = """\
Design Document: Zone-Level Playback Configuration

1. Objective
Enable configuration of playback quality limits at the zone (region) level via CMS,
store them in the database, and expose them in the Platform Settings API within the
existing regions object.
The system will support:
  - Maximum video height (maxVideoHeight)
  - Maximum video bitrate (maxVideoBitrateKBPS)

2. CMS Changes

2.1 Scope
Enhance the Regions module to allow administrators to configure playback limits.
Affected Screens: Regions List (View), Add Region, Edit Region.

2.2 New Configuration Fields

2.2.1 Max Video Height
  Display Label: Max Video Height
  Field Type: Radio Buttons
  Recommended Field Name: max_video_height
  Database Field Name: maxVideoHeight
  Data Type: Integer
  Allowed Values: 480 (Default), 720, 1080
  Description: Defines the maximum allowed video resolution height (in pixels).

2.2.2 Max Video Bitrate
  Display Label: Max Video Bitrate (kbps)
  Field Type: Radio Buttons
  Recommended Field Name: max_video_bitrate_kbps
  Database Field Name: maxVideoBitrateKBPS
  Data Type: Integer
  Allowed Values: 1500 (Default), 3000, 5000
  Description: Defines the maximum allowed video bitrate (in kbps).

2.3 Default Behavior
  If no value is selected: maxVideoHeight = 480, maxVideoBitrateKBPS = 1500

2.4 Edit & View Behavior
  Existing values must be loaded from stored configurations and pre-selected in CMS forms.
  Missing values should default automatically.

2.5 Validation Rules
  Height: only 480, 720, 1080 allowed. Invalid inputs fallback to defaults.
  Bitrate: only 1500, 3000, 5000 allowed. Invalid inputs fallback to defaults.

3. Database Changes

3.1 Schema Impact: No new columns required.

3.2 Storage Location
  Table: regions
  Column: configurations (JSON)

3.3 Data Structure
  {"maxVideoHeight": 720, "maxVideoBitrateKBPS": 3000}

3.4 Seeder Updates
  Default values must be included: maxVideoHeight = 480, maxVideoBitrateKBPS = 1500

3.5 Backward Compatibility
  Existing records without these fields must continue to function.
  Defaults must be applied dynamically.

4. API Changes

4.1 Affected API
  Endpoint: /v3/auth/platform_settings

4.2 Existing Response Structure
  The API currently returns regions as:
  {
    "regions": [
      {
        "region_code": "int", "region": "International",
        "download_screen_image": "", "hls_playback_url": "", "dash_playback_url": "",
        "operators_available": 1, "prefix_currency": "$", "suffix_currency": "",
        "muturity_ratings": [], "logo": ""
      }
    ]
  }

4.3 Updated Response Structure
  Add the following fields inside each region object: maxVideoHeight, maxVideoBitrateKBPS

4.4 Final Response Example
  {
    "regions": [{
      "region_code": "int", "region": "International",
      "download_screen_image": "", "hls_playback_url": "", "dash_playback_url": "",
      "operators_available": 1, "prefix_currency": "$", "suffix_currency": "",
      "muturity_ratings": [
        {"title": "Kids", "target_age": "4", "translation_key": ""},
        {"title": "13+",  "target_age": "13", "translation_key": ""},
        {"title": "16+",  "target_age": "16", "translation_key": ""},
        {"title": "18+",  "target_age": "18", "translation_key": ""}
      ],
      "logo": "d2f2909e005bf0b0f0ba8a916b10b310254a04e4.png",
      "maxVideoHeight": 720,
      "maxVideoBitrateKBPS": 3000
    }]
  }

4.5 API Behavior
  Values must be derived from configurations JSON.
  If values are missing: return defaults maxVideoHeight=480, maxVideoBitrateKBPS=1500.

4.6 Backward Compatibility
  Existing clients will not be impacted (fields are additive).
  New clients can use these fields for playback filtering.

5. Client-Side Enforcement (Reference)
  Clients must filter playback renditions using:
    rung.height <= maxVideoHeight
    rung.bitrate_kbps <= maxVideoBitrateKBPS
  Both conditions must be satisfied when both values are present.

6. Edge Cases & Considerations
  - Missing configurations → use defaults
  - Partial configurations → fill missing fields only
  - Invalid values → fallback to defaults
  - Ensure JSON merging (do not overwrite existing keys)
"""
# ─────────────────────────────────────────────────────────────────────────────


# ── Logging helpers ───────────────────────────────────────────────────────────
WIDTH = 70

def header(title: str, char: str = "="):
    print(f"\n{char * WIDTH}")
    print(f"  {title}")
    print(f"{char * WIDTH}")

def subheader(title: str):
    header(title, char="─")

def log(msg: str, indent: int = 2):
    prefix = " " * indent
    for line in msg.splitlines():
        print(f"{prefix}{line}")

def log_list(items, indent: int = 4, empty_msg: str = "(none)"):
    if not items:
        print(f"{' ' * indent}{empty_msg}")
    for item in items:
        print(f"{' ' * indent}• {item}")

def wrap(text: str, width: int = WIDTH - 6, indent: int = 4) -> str:
    return textwrap.fill(str(text), width=width,
                         initial_indent=" " * indent,
                         subsequent_indent=" " * indent)

def ts() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


# ── Init ──────────────────────────────────────────────────────────────────────
header("TV2Z Multi-Agent Pipeline — End-to-End Test")
log(f"Started : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
log(f"Issue   : {ISSUE_TITLE}")
log(f"API repo: {API_REPO}")
log(f"CMS repo: {CMS_REPO}")
log(f"Create PR: {CREATE_PR}")

llm = load_llm()
log(f"LLM     : {type(llm).__name__}  model={llm._model}")

gh = GitHubAdapter()


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 0 — MetaPlannerAgent
# ══════════════════════════════════════════════════════════════════════════════
header("STAGE 0 — MetaPlannerAgent")
log("What it does: reads the full requirement + API.md + CMS.md, decides which")
log("              repo(s) need changes, produces focused per-repo specs, and")
log("              determines execution order (data-owner repo first).")

if TEST_SINGLE_REPO:
    log(f"\n[OVERRIDE] TEST_SINGLE_REPO='{TEST_SINGLE_REPO}' — skipping MetaPlanner")
    from core.agents.meta_planner import MetaPlan
    meta_plan = MetaPlan(
        repos=[TEST_SINGLE_REPO],
        api_spec=ISSUE_DESCRIPTION if TEST_SINGLE_REPO == "api" else "",
        cms_spec=ISSUE_DESCRIPTION if TEST_SINGLE_REPO == "cms" else "",
        shared_context="",
        reasoning="forced single-repo override",
    )
else:
    print(f"\n  [{ts()}] Calling MetaPlannerAgent...")
    meta_planner = MetaPlannerAgent(llm)
    meta_plan = meta_planner.plan(ISSUE_TITLE, ISSUE_DESCRIPTION)

subheader("MetaPlanner output")
log(f"Repos (execution order) : {meta_plan.repos}")
log(f"Reasoning               : {meta_plan.reasoning}")

if meta_plan.shared_context:
    log("\nShared context (field names/defaults both repos must agree on):")
    log(meta_plan.shared_context, indent=4)

if meta_plan.api_spec:
    log("\nAPI spec (focused description for Node.js repo):")
    log(wrap(meta_plan.api_spec))

if meta_plan.cms_spec:
    log("\nCMS spec (focused description for PHP/Laravel repo):")
    log(wrap(meta_plan.cms_spec))

if meta_plan.api_keywords:
    log(f"\nAPI search keywords (runtime-focused, from MetaPlanner): {meta_plan.api_keywords}")
if meta_plan.cms_keywords:
    log(f"CMS search keywords (runtime-focused, from MetaPlanner): {meta_plan.cms_keywords}")


# ══════════════════════════════════════════════════════════════════════════════
# Per-repo pipeline
# ══════════════════════════════════════════════════════════════════════════════
completed: dict[str, dict] = {}   # stores results from completed repos

def build_cross_repo_context(completed: dict, shared_context: str) -> str:
    if not completed:
        return ""
    parts = []
    if shared_context:
        parts.append(f"Shared context agreed by both repos:\n{shared_context}")
    for repo_type, result in completed.items():
        plan = result.get("plan")
        if plan:
            parts.append(
                f"{repo_type.upper()} repo (already completed):\n"
                f"  Files targeted : {plan.target_files}\n"
                f"  Keywords used  : {plan.keywords_extracted}\n"
                f"  Reasoning      : {plan.reasoning}"
            )
    return "\n\n".join(parts)


for REPO_TYPE in meta_plan.repos:
    repo   = REPO_MAP[REPO_TYPE]
    branch = BRANCH_MAP[REPO_TYPE]
    spec   = meta_plan.spec_for(REPO_TYPE)
    lang   = "Node.js / JavaScript" if REPO_TYPE == "api" else "PHP 8.2 / Laravel 10"
    cross_repo_ctx = build_cross_repo_context(completed, meta_plan.shared_context)

    banner = f"REPO: {REPO_TYPE.upper()}  ({lang})  →  {repo}"
    header(banner, char="█")

    # ── STAGE 1: PlannerAgent ─────────────────────────────────────────────────
    subheader(f"STAGE 1 — PlannerAgent [{REPO_TYPE}]")
    log("What it does: extracts keywords from the focused spec, searches the repo's")
    log(f"              knowledge graph ({REPO_TYPE} graph), returns files to fix.")

    if cross_repo_ctx:
        log("\nCross-repo context passed to PlannerAgent:")
        for line in cross_repo_ctx.splitlines():
            log(line, indent=4)

    seed_kws = meta_plan.keywords_for(REPO_TYPE)
    if seed_kws:
        log(f"\nSeed keywords from MetaPlanner (used first): {seed_kws}")

    print(f"\n  [{ts()}] Searching graph_{REPO_TYPE}/graph.json...")
    nav     = get_navigator(REPO_TYPE)
    planner = PlannerAgent(llm, nav)
    plan    = planner.plan(ISSUE_TITLE, spec or ISSUE_DESCRIPTION,
                           cross_repo_context=cross_repo_ctx,
                           seed_keywords=seed_kws)

    subheader(f"PlannerAgent [{REPO_TYPE}] output")
    log(f"Keywords extracted : {plan.keywords_extracted}")
    log(f"Change type        : {plan.change_type}")
    log(f"Affected communities: {plan.affected_communities}")
    log(f"Reasoning          : {plan.reasoning}")
    log(f"\nTarget files ({len(plan.target_files)}):")
    log_list(plan.target_files)

    if not plan.target_files:
        log("\n[!] No files found in graph — using placeholder file for next steps.")
        placeholder = "services/platform_settings.js" if REPO_TYPE == "api" \
                      else "app/Livewire/Regions.php"
        plan.target_files = [placeholder]

    # ── STAGE 2: GitHub Fetch ─────────────────────────────────────────────────
    subheader(f"STAGE 2 — GitHub Fetch [{REPO_TYPE}]")
    log(f"What it does: fetches real file content from GitHub ({repo})")
    log(f"              branch: {branch}")

    code_sections: dict[str, str] = {}
    for path in plan.target_files[:MAX_FILES]:
        print(f"\n  [{ts()}] Fetching: {path}")
        try:
            content = gh.get_file(repo, path, branch)
            code_sections[path] = content
            log(f"✓ {path}  ({len(content):,} chars)", indent=4)
        except Exception as e:
            code_sections[path] = f"// file not found in {repo}: {path} ({e})"
            log(f"✗ {path}  → not found: {e}", indent=4)

    # ── STAGE 3: GraphNavigator line filter (hint only with 1M context) ─────────
    subheader(f"STAGE 3 — Graph Line Filter [{REPO_TYPE}]")
    log("What it does: with gpt-4.5 1M token context, full files are sent.")
    log("              Graph filter runs for logging only — not used to truncate.")

    for path, content in code_sections.items():
        if not content.startswith("// file not found"):
            log(f"{path}: {content.count(chr(10))+1} lines (full file sent to Explorer)",
                indent=4)

    # ── STAGE 4: ExplorerAgent ────────────────────────────────────────────────
    subheader(f"STAGE 4 — ExplorerAgent [{REPO_TYPE}]")
    log("What it does: reads the FULL file content in READ-ONLY mode,")
    log("              labels each file must_change or context_only.")

    print(f"\n  [{ts()}] Running ExplorerAgent...")
    explorer        = ExplorerAgent(llm)
    explorer_result = explorer.explore(ISSUE_TITLE, spec or ISSUE_DESCRIPTION,
                                       code_sections)   # full content, not filtered

    subheader(f"ExplorerAgent [{REPO_TYPE}] output")
    log(f"Summary: {explorer_result.summary}")
    log(f"\nMust change ({len(explorer_result.must_change_files)}):")
    log_list(list(explorer_result.must_change_files.keys()))
    log(f"\nContext only ({len(explorer_result.context_files)}):")
    log_list(list(explorer_result.context_files.keys()))

    # ── STAGE 5: CoderAgent ───────────────────────────────────────────────────
    subheader(f"STAGE 5 — CoderAgent [{REPO_TYPE}]  ({lang})")
    log(f"What it does: generates surgical code edits in {lang}.")
    log("              Receives must_change files + context files (labelled).")
    log("              Outputs {path, old_string, new_string} edits + confidence.")

    coder_input = {
        **explorer_result.must_change_files,
        **{f"[CONTEXT] {p}": v for p, v in explorer_result.context_files.items()},
    }

    print(f"\n  [{ts()}] Running CoderAgent ({lang})...")
    coder        = CoderAgent(llm)
    coder_result = coder.generate(
        title=ISSUE_TITLE,
        description=spec or ISSUE_DESCRIPTION,
        code_context=coder_input,
        base_files=code_sections,
        repo_type=REPO_TYPE,
    )

    subheader(f"CoderAgent [{REPO_TYPE}] output")
    log(f"Confidence : {coder_result.confidence:.2f}")
    log(f"Reasoning  :")
    log(wrap(coder_result.reasoning))

    log(f"\nSurgical edits ({len(coder_result.edits)}):")
    for i, edit in enumerate(coder_result.edits, 1):
        path = edit.get("path", "?")
        old  = edit.get("old_string", "")
        new  = edit.get("new_string", "")
        print(f"\n    Edit {i} → {path}")
        print(f"    {'─' * (WIDTH - 10)}")
        print("    REMOVE:")
        for line in old.splitlines()[:6]:
            print(f"      {line}")
        if old.count("\n") > 5:
            print(f"      ... ({old.count(chr(10))+1} lines total)")
        print("    ADD:")
        for line in new.splitlines()[:6]:
            print(f"      {line}")
        if new.count("\n") > 5:
            print(f"      ... ({new.count(chr(10))+1} lines total)")

    log(f"\nFiles that will change: {list(coder_result.file_contents.keys())}")

    if coder_result.regression_test:
        log("\nRegression test snippet:")
        log(wrap(coder_result.regression_test))

    # ── STAGE 6: ReviewerAgent ────────────────────────────────────────────────
    subheader(f"STAGE 6 — ReviewerAgent [{REPO_TYPE}]")
    log("What it does: adversarial review — tries to find what's wrong.")
    log("              Checks: Correctness, Security, Regression, Boundaries,")
    log("              Error handling, Concurrency.")
    log("              PASS → done  |  FAIL/PARTIAL → feedback to retry")

    print(f"\n  [{ts()}] Running ReviewerAgent...")
    reviewer        = ReviewerAgent(llm)
    reviewer_result = reviewer.review(
        description=spec or ISSUE_DESCRIPTION,
        original_code=explorer_result.must_change_files,
        proposed_changes=coder_result.file_contents,
    )

    subheader(f"ReviewerAgent [{REPO_TYPE}] output")
    verdict_sym = "✓" if reviewer_result.approved else "✗"
    log(f"Verdict     : {verdict_sym}  {reviewer_result.verdict}")
    log(f"Approved    : {reviewer_result.approved}")
    log(f"Security OK : {reviewer_result.security_ok}")

    if reviewer_result.checks:
        log("\nPer-check results:")
        for check, outcome in reviewer_result.checks.items():
            status = "✓" if "PASS" in str(outcome).upper() else "✗"
            log(f"{status}  {check:<22} {outcome}", indent=4)

    if reviewer_result.feedback:
        log("\nFeedback:")
        log(wrap(reviewer_result.feedback, width=WIDTH - 8, indent=4))

    # ── STAGE 7: GitHub PR (optional) ─────────────────────────────────────────
    pr_url = None
    if CREATE_PR and coder_result.file_contents:
        subheader(f"STAGE 7 — GitHub PR [{REPO_TYPE}]")
        log(f"Creating branch + commit + Draft PR on {repo}")

        try:
            slug        = re.sub(r"[^a-z0-9]+", "-", ISSUE_TITLE.lower())[:40].strip("-")
            branch_name = f"autofix/{slug}-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
            print(f"\n  [{ts()}] Creating branch: {branch_name}")
            gh.create_branch(repo, branch_name, branch)

            print(f"  [{ts()}] Committing {len(coder_result.file_contents)} file(s)...")
            gh.commit_changes(
                repo=repo,
                branch=branch_name,
                files=coder_result.file_contents,
                message=f"autofix: {ISSUE_TITLE}",
            )

            # ── Code changes block — only edits that were actually committed ──
            # coder_result.edits contains ALL proposed edits; only show the ones
            # whose path is in coder_result.file_contents (i.e. old_string matched).
            committed_paths = set(coder_result.file_contents.keys())
            code_changes_md = ""
            applied_edits = [e for e in coder_result.edits
                             if e.get("path", "") in committed_paths]
            if applied_edits:
                parts = []
                for edit in applied_edits:
                    path       = edit.get("path", "?")
                    old_string = edit.get("old_string", "")
                    new_string = edit.get("new_string", "")
                    diff_lines = []
                    for line in old_string.splitlines():
                        diff_lines.append(f"- {line}")
                    for line in new_string.splitlines():
                        diff_lines.append(f"+ {line}")
                    parts.append(
                        f"**`{path}`**\n```diff\n" + "\n".join(diff_lines) + "\n```"
                    )
                code_changes_md = "\n\n## Code Changes\n\n" + "\n\n".join(parts)

            # ── Reviewer checks block ────────────────────────────────────
            checks_md = ""
            if reviewer_result.checks:
                rows      = "\n".join(f"| {k} | {v} |" for k, v in reviewer_result.checks.items())
                checks_md = f"\n\n## AI Code Review — Per-Check Results\n| Check | Result |\n|---|---|\n{rows}"

            review_feedback_md = ""
            if reviewer_result.feedback:
                review_feedback_md = f"\n\n**Reviewer feedback:** {reviewer_result.feedback}"

            pr_body = (
                f"## Summary\n{coder_result.reasoning}\n\n"
                f"## Repo\n`{REPO_TYPE}` — {lang}\n\n"
                f"## Files Changed\n"
                + "\n".join(f"- `{f}`" for f in coder_result.file_contents)
                + code_changes_md
                + f"\n\n## AI Code Review\n"
                f"**Verdict:** {reviewer_result.verdict}  \n"
                f"**Security OK:** {reviewer_result.security_ok}  \n"
                f"**Confidence:** {coder_result.confidence:.0%}"
                + review_feedback_md
                + checks_md
                + "\n\n---\n"
                f"> Auto-generated by multi-agent pipeline. Requires human review before merge."
            )

            pr = gh.create_pr(PRModel(
                title=f"[AutoFix] {ISSUE_TITLE} [{REPO_TYPE.upper()}]",
                body=pr_body,
                branch_name=branch_name,
                base_branch=branch,
                repo=repo,
                reviewer="",
                zoho_issue_id="test",
                draft=True,
            ))
            pr_url = pr.url
            log(f"\nDraft PR created: {pr_url}")

        except Exception as e:
            log(f"\n[!] PR creation failed: {e}")

    # Store completed result so next repo can see it
    completed[REPO_TYPE] = {
        "plan"            : plan,
        "code_sections"   : code_sections,
        "explorer_result" : explorer_result,
        "coder_result"    : coder_result,
        "reviewer_result" : reviewer_result,
        "pr_url"          : pr_url,
    }

    log(f"\n[{ts()}] {REPO_TYPE.upper()} pipeline complete.")


# ══════════════════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
header("FINAL SUMMARY")
log(f"Requirement : {ISSUE_TITLE}")
log(f"Repos ran   : {list(completed.keys())}")
print()

for repo_type, result in completed.items():
    plan     = result["plan"]
    explorer = result["explorer_result"]
    coder    = result["coder_result"]
    reviewer = result["reviewer_result"]
    pr_url   = result["pr_url"]
    verdict_sym = "✓" if reviewer.approved else "✗"

    log(f"{'─' * (WIDTH - 4)}")
    log(f"[{repo_type.upper()}]  {REPO_MAP[repo_type]}")
    log(f"  PlannerAgent  → {len(plan.target_files)} files identified")
    log(f"                  keywords: {plan.keywords_extracted}")
    log(f"  ExplorerAgent → {len(explorer.must_change_files)} must change, "
        f"{len(explorer.context_files)} context only")
    log(f"  CoderAgent    → {len(coder.file_contents)} file(s) fixed  "
        f"(confidence {coder.confidence:.2f})")
    log(f"  ReviewerAgent → {verdict_sym}  {reviewer.verdict}  "
        f"(security_ok={reviewer.security_ok})")
    if pr_url:
        log(f"  PR            → {pr_url}")
    print()

if len(completed) > 1:
    log("Cross-repo context was passed between pipelines — field names and")
    log("data structures are aligned across both repos.")
