# Multi-Agent Code-Fix System

## What This Does

When a user submits a requirement (bug report or feature request), the system automatically:
1. Reads `API.md` + `CMS.md` to understand both repos, then decides which repo(s) need changes
2. For each target repo, produces a focused, repo-specific change specification
3. Searches the repo's knowledge graph to find the exact files to touch
4. Reads those files from GitHub
5. Filters to only the relevant lines (graph-based + AI-based)
6. Generates a code fix in the correct language (Node.js or PHP/Laravel)
7. Adversarially reviews the fix — loops up to 3 times if rejected
8. Creates a Draft PR per repo, with the second repo's agent aware of what the first did

---

## Two-Repo Architecture

The system manages two separate codebases:

| Repo | Language | Graph | GitHub |
|---|---|---|---|
| **API** | Node.js 18 / Express.js | `graph_api/graph.json` (2,211 nodes) | `ashok-potnuru/hackathon_wlb_api` |
| **CMS** | PHP 8.2 / Laravel 10 | `graph_cms/graph.json` (8,402 nodes) | `ashok-potnuru/hackathon_wlb_cms` |

Context for each repo lives in `API.md` (stack, routes, entry points) and `CMS.md` (paths, patterns, migration rules).

---

## Agent Pipeline

```
User Requirement (from Zoho ticket or direct prompt)
      │
      ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 0 — MetaPlannerAgent                         │
│                                                     │
│  Reads full requirement + API.md + CMS.md           │
│  Decides: which repo(s) need changes?               │
│  Produces per-repo focused specs                    │
│  Determines execution order (data-owner first)      │
│                                                     │
│  Output: MetaPlan {                                 │
│    repos: ["cms", "api"],  ← ordered               │
│    cms_spec: "precise CMS-only change description", │
│    api_spec: "precise API-only change description", │
│    shared_context: "field names, defaults, types"   │
│  }                                                  │
└─────────────────────────────────────────────────────┘
      │
      │  For each repo in meta_plan.repos (in order):
      ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 1 — PlannerAgent  (per repo)                 │
│                                                     │
│  Input: focused repo spec + cross_repo_context      │
│         (cross_repo = what the prev repo planned)   │
│                                                     │
│  LLM extracts keywords from focused spec            │
│  GraphNavigator.search_nodes(keywords)              │
│    → reads graph_api/ or graph_cms/ graph.json      │
│    → finds matching nodes by keyword substring      │
│  GraphNavigator.get_related_files()                 │
│    → BFS through edges → related files (max 15)     │
│                                                     │
│  Output: PlanResult(target_files, keywords)         │
└─────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 2 — GitHub Fetch                             │
│                                                     │
│  vc.get_file(repo, path, branch) for each file      │
│  → full file content fetched from GitHub            │
└─────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 3 — GraphNavigator line filter (deterministic)│
│                                                     │
│  Uses source_location (line numbers) from graph     │
│  → extracts lines around matched functions/classes  │
│  → merges overlapping ranges, adds line # prefixes  │
└─────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 4 — ExplorerAgent  (AI, strict read-only)    │
│                                                     │
│  Reads graph-filtered code sections                 │
│  → decides which files MUST change vs context only  │
│  → labels: must_change / context_only               │
│  Cannot suggest fixes — read-only enforced in prompt│
└─────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 5 — CoderAgent  (AI, language-aware)         │
│                                                     │
│  repo_type="api"  → Node.js/Express expert prompt   │
│  repo_type="cms"  → PHP 8.2/Laravel 10 expert prompt│
│                     (Eloquent, Blade, Livewire,      │
│                      Stancl/Tenancy patterns)        │
│                                                     │
│  Receives must_change + context_only files          │
│  Generates surgical edits: {path, old_str, new_str} │
│  _apply_edits() does str_replace on full files      │
│  Returns confidence score (0.0–1.0)                 │
└─────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 6 — ReviewerAgent  (AI, adversarial)         │
│                                                     │
│  6 structured checks:                               │
│    ✓ Correctness   ✓ Security    ✓ Regression risk  │
│    ✓ Boundary vals ✓ Error hdlg  ✓ Concurrency      │
│                                                     │
│  PASS   → proceed to PR                             │
│  FAIL / PARTIAL → feedback to CoderAgent (retry)    │
│  security_ok=False → hard stop (SecurityScanError)  │
│  max 3 attempts                                     │
└─────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────┐
│  STAGE 7 — Draft PR created on GitHub               │
│                                                     │
│  Branch: autofix/<slug>-<timestamp>                 │
│  Body includes: reasoning, files changed,           │
│  AI review verdict + checks table, confidence %     │
└─────────────────────────────────────────────────────┘
      │
      │  (if both repos needed: repeat stages 1–7 for
      │   second repo, with first repo's plan as context)
      ▼
    Done — one Draft PR per repo
```

---

## Example: Cross-Repo Feature (Zone Playback Config)

Requirement: Add `maxVideoHeight` + `maxVideoBitrateKBPS` to CMS Regions form, store in DB, expose in API.

```
MetaPlannerAgent
  → repos: ["cms", "api"]   ← CMS first (owns the data)
  → cms_spec: "Add maxVideoHeight radio (480/720/1080) and maxVideoBitrateKBPS
               radio (1500/3000/5000) to Regions Add/Edit forms.
               Store in regions.configurations JSON column. Add seeder defaults."
  → api_spec: "Read maxVideoHeight and maxVideoBitrateKBPS from
               regions.configurations JSON. Expose in /v3/auth/platform_settings
               inside each region object. Default 480/1500 if missing."
  → shared_context: "fields: maxVideoHeight (int), maxVideoBitrateKBPS (int),
                     stored in regions.configurations JSON,
                     defaults: 480 / 1500"

CMS PlannerAgent (graph_cms, no cross_repo yet)
  → keywords: ["regions", "livewire", "configurations", "seeder"]
  → target files: [app/Livewire/Regions.php, database/seeders/RegionsSeeder.php, ...]
  → CMS pipeline runs → PHP fix → PR #1

API PlannerAgent (graph_api, cross_repo = CMS plan above)
  → knows exact field names CMS used (maxVideoHeight, maxVideoBitrateKBPS)
  → keywords: ["platform_settings", "regions", "configurations", "auth"]
  → target files: [services/platform_settings.js, dal/regions.js, ...]
  → API pipeline runs → Node.js fix → PR #2
```

---

## Files & Directory Structure

```
core/
├── agents/
│   ├── base_agent.py           # Wraps LLM adapter with run_turn() + cache_control
│   ├── meta_planner.py         # ★ NEW — Stage 0: per-repo specs + execution order
│   ├── planner_agent.py        # Stage 1: keywords → graph search → target files
│   │                           #          accepts cross_repo_context param
│   ├── explorer_agent.py       # Stage 4: read-only, labels must_change vs context
│   ├── coder_agent.py          # Stage 5: language-aware surgical edits
│   │                           #          repo_type="api" → JS prompt
│   │                           #          repo_type="cms" → PHP/Laravel prompt
│   ├── reviewer_agent.py       # Stage 6: adversarial 6-check review
│   └── repo_router.py          # Thin router (superseded by MetaPlannerAgent;
│                               #   kept for standalone use)
├── utils/
│   └── graph_navigator.py      # Dual-graph: get_navigator("api"|"cms")
│                               #   GRAPH_API_PATH → graph_api/graph.json
│                               #   GRAPH_CMS_PATH → graph_cms/graph.json
└── stages/
    └── agent_runner.py         # ★ UPDATED — orchestrates MetaPlanner + per-repo pipelines

scripts/
├── agents_pipeline.py          # ★ UPDATED — run(repo_type, cross_repo_context)
├── _llm_loader.py              # Provider/model loader from settings.yaml
└── test_agents_live.py         # End-to-end test

graph_api/                      # ★ RENAMED from tv2z_codebase_graph/
├── graph.json                  # API graph — 2,211 nodes, 3,142 edges, 386 communities
├── GRAPH_REPORT.md
├── graph.html
└── cache/

graph_cms/                      # ★ RENAMED from graphify-out/
├── graph.json                  # CMS graph — 8,402 nodes, 14,267 edges, 800 communities
├── GRAPH_REPORT.md
├── graph.html
└── cache/

API.md                          # API repo context (stack, routes, entry points, graph location)
CMS.md                          # CMS repo context (paths, patterns, migration rules, graph location)
```

---

## Configuration

### `.env`
```
API_REPO=ashok-potnuru/hackathon_wlb_api   # Node.js API repo
CMS_REPO=ashok-potnuru/hackathon_wlb_cms   # PHP/Laravel CMS repo
```

### `settings.yaml`
```yaml
llm: openai          # claude | openai | gemini
model: gpt-4o
default_repos:
  api: TV2Z-IND/wlb_api    # production API repo
  cms: TV2Z-IND/wlb_cms    # production CMS repo
default_branch: master
```

---

## How graph.json Files Are Loaded

Each graph is generated by running `/graphify` on the respective codebase and committing the output.

```
graph_api/graph.json   ← run /graphify on hackathon_wlb_api  (Node.js)
graph_cms/graph.json   ← run /graphify on hackathon_wlb_cms  (PHP/Laravel)
```

`get_navigator("api")` and `get_navigator("cms")` return separate singletons, each loading their own graph once and caching in memory.

When the target codebase changes significantly → re-run `/graphify` → replace the relevant `graph_*/graph.json`.

---

## How graph.json Filters File Contents (Smart Extraction)

Instead of blindly sending full files, we extract only relevant lines using graph node line numbers.

```
Issue: "Add maxVideoHeight field to regions API response"
         │
         ▼
MetaPlannerAgent → cms_spec + api_spec (focused per repo)
         │
         ▼
PlannerAgent(api) → keywords: ["platform_settings", "regions", "configurations"]
         │
         ▼
GraphNavigator("api").search_nodes(keywords)
→ finds node: getPlatformSettings() at L87 in services/platform_settings.js  (score: 3)
         │
         ▼
GraphNavigator.get_related_files(seeds, max_hops=2, max_files=15)
→ BFS via calls/references edges → [platform_settings.js, dal/regions.js, ...]
         │
         ▼
GitHub API → fetch FULL file content for each path
         │
         ▼
GraphNavigator.get_relevant_lines(file_path, full_content, keywords)
→ extracts lines 77–127 (L87 ± 40 context lines)
→ sends ONLY those lines to ExplorerAgent (with line number prefixes)
→ line number prefixes STRIPPED before CoderAgent sees the code

77| function getPlatformSettings(operatorId) {   ← ExplorerAgent sees this
...
function getPlatformSettings(operatorId) {       ← CoderAgent sees this (clean)
```

**Fallback:** if no graph nodes match keywords for a file → sends first 3000 chars.

---

## ReviewerAgent — Adversarial Checks

| Check | What it looks for |
|---|---|
| Correctness | Does the fix address the root cause, not just the symptom? |
| Security | SQL injection, XSS, auth bypass, unvalidated input, data exposure |
| Regression risk | Callers of changed functions that could silently break |
| Boundary values | null, undefined, empty string, 0, negative numbers |
| Error handling | Errors caught and handled, not silently swallowed |
| Concurrency | Parallel calls — state corruption or deadlock risk |

**VERDICT:**
- `PASS` → approved, proceed to PR
- `FAIL / PARTIAL` → feedback sent back to CoderAgent (retry, max 3)
- `security_ok: false` → hard stop, `SecurityScanError` raised

---

## Agent Roles Summary

| Agent | File | Role |
|---|---|---|
| MetaPlannerAgent | `core/agents/meta_planner.py` | Reads API.md + CMS.md, routes requirement, produces focused per-repo specs |
| PlannerAgent | `core/agents/planner_agent.py` | Keywords → graph search → target files (per repo) |
| ExplorerAgent | `core/agents/explorer_agent.py` | Read-only; labels files must_change vs context_only |
| CoderAgent | `core/agents/coder_agent.py` | Language-aware surgical edits (Node.js or PHP/Laravel) |
| ReviewerAgent | `core/agents/reviewer_agent.py` | Adversarial 6-check review, retry loop |

---

## Running Tests

```bash
# Step 1 — activate environment once per session
source venv/bin/activate
set -a && source .env && set +a

# Unit tests — no API key needed
pytest tests/test_agents.py -v
pytest tests/test_orchestrator.py -v
pytest tests/test_graph_navigator.py -v

# Test each agent individually (real LLM calls)
python3 scripts/test_planner.py
python3 scripts/test_explorer.py
python3 scripts/test_coder.py
python3 scripts/test_reviewer.py

# Full end-to-end: MetaPlanner → per-repo pipelines → GitHub PRs
python3 scripts/test_agents_live.py
```

To switch LLM provider/model — edit `settings.yaml`:
```yaml
llm: openai          # claude | openai | gemini
model: gpt-4o        # gpt-4o-mini, claude-sonnet-4-6, etc.
```
