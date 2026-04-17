# AutoFix AI — Architecture & Walkthrough

## What Is This Project?

**AutoFix AI** — a system that automatically fixes bugs and implements features.

When someone creates a bug ticket in Zoho, the system reads it, uses Claude AI to write a code fix, opens a Draft Pull Request on GitHub, and notifies the team on Microsoft Teams — all without human involvement.

---

## The 8-Stage Pipeline

Every bug or feature goes through these stages in order:

```
1. INTAKE          → Read the ticket. Is it clear enough to work with?
2. TRIAGE          → Can AI actually fix this? Which repo is affected?
3. RESEARCH        → Fetch the relevant code. Look up similar past fixes.
4. FIX GENERATION  → Ask Claude to write the fix. Security-check it. Retry if bad.
5. PR CREATION     → Create a branch, commit the fix, open a Draft PR on GitHub.
         ── human reviews the PR ──
6. DEVELOPER REVIEW → Developer left feedback? Re-generate the fix to address it.
7. CI               → Tests passed? Mark Validating. Failed? Post diagnosis.
8. CLOSURE          → PR merged? Mark ticket Fixed. Store fix for future learning.
```

Stages 1–5 run automatically when a Zoho webhook fires.
Stages 6–8 run automatically when GitHub fires webhooks (review comment, CI result, merge).

---

## Config Files

### `settings.yaml` — choose your providers
```yaml
llm: claude           # which AI to use
issue_tracker: zoho   # where bug reports come from
version_control: github
notification: teams
cloud: aws
vector_store: chromadb
```
Change one line to swap the entire provider. No code changes needed.

### `.env` (copy from `.env.example`) — your secrets
```
ANTHROPIC_API_KEY    → to call Claude AI
ZOHO_CLIENT_ID etc.  → to read/update Zoho tickets
GITHUB_TOKEN         → to create branches and PRs
TEAMS_WEBHOOK_URL    → to post messages to Teams
AWS_SQS_QUEUE_URL    → the job queue URL
ZOHO_PORTAL_ID       → for Zoho Projects (Tasks)
```

---

## How a Job Travels Through the System

### 1. Webhook Server (`api/webhook_server.py`)

Receives incoming webhooks from external services:

| Endpoint | When it fires |
|---|---|
| `POST /webhook/zoho` | Zoho Desk ticket created/updated |
| `POST /webhook/zoho/task` | Zoho Projects task created with PRD attached |
| `POST /webhook/github` | GitHub PR review, CI result, or merge |

The server does **only one thing**: puts a job on the AWS SQS queue and returns HTTP 200 immediately. It never runs the pipeline — that would block.

### 2. Queue (`core/queue/producer.py` → AWS SQS)

Job payload structure:
```python
{
  "issue_id": "123456",
  "source": "zoho",   # zoho | zoho_task | github_ci | github_review | github_merge
  "payload": { ...webhook body... },
  "tenant": "team_payments"
}
```

### 3. Worker (`core/queue/worker.py`)

A long-running background process:
1. Polls SQS every 5 seconds
2. Grabs a job → runs the full pipeline
3. On success → deletes the job from the queue
4. On crash → logs the error, sends a Teams alert, leaves the job for retry

---

## The Context Dict (How Stages Share Data)

Each stage receives a `context` dict and returns an enriched version. It grows as it moves through the pipeline:

```
Starts as:      { payload, adapters, tenant, trace_id }
After Intake:   + { issue, work_type }
After Triage:   + { issue.affected_repos, issue.target_branch }
After Research: + { research: {code_context, similar_fixes} }
After Fix Gen:  + { fix }
After PR:       + { pr }
```

---

## Each Stage Explained

### INTAKE (`core/stages/intake.py`)
- Loads the full ticket from Zoho by ID
- If it's a Zoho Task: downloads PDF/DOCX attachments, extracts the PRD text
- Asks Claude: *"FIXABLE or VAGUE?"* (one word answer)
- If VAGUE → posts comment asking for more detail, sets status "Needs Clarification", stops
- Sets `work_type = "feature"` (Zoho task) or `"bugfix"` (Zoho Desk ticket)

### TRIAGE (`core/stages/triage.py`)
- Asks Claude: *"Is this fixable by code changes? List affected repos."*
- Parses Claude's reply for `FIXABLE: YES` and `REPOS: owner/repo`
- If not fixable → marks "Needs Manual Review", stops
- Sets target branch: `main` for critical bugs, `develop` for everything else
- Updates Zoho to "In Progress"

### RESEARCH (`core/stages/research.py`)
- Searches ChromaDB for the 3 most similar past fixes
- Lists all files in the repo, asks Claude: *"Which 5 files likely contain the bug?"*
- Fetches those file contents from GitHub
- If more than 5 files would change → stops (too risky for automation)

### FIX GENERATION (`core/stages/fix_generator.py`)
- Sends Claude: issue + relevant code + similar past fixes
- Claude returns JSON:
  ```json
  {
    "reasoning": "The bug is caused by...",
    "files": { "src/auth.py": "...new file content..." },
    "regression_test": "def test_login(): ...",
    "confidence": 0.85
  }
  ```
- Runs a security review pass on the generated fix
- If confidence < 40% → retries (up to 3 total attempts)

### PR CREATION (`core/stages/pr_creator.py`)
- Creates branch `autofix/{issue_id}`, commits the changed files
- Runs git blame → assigns the author of the changed code as reviewer
- Opens a **Draft PR** with: root cause, files changed, confidence %, regression test, rollback instructions, link to Zoho ticket
- Updates Zoho to "Fix Proposed", posts comment, sends Teams message

### DEVELOPER REVIEW (`core/stages/reviewer_handler.py`)
- Triggered when a developer leaves a review comment on the PR
- Feeds the comment back to Claude → generates updated fix → commits to same branch
- Updates Zoho to "Under Review"

### CI (`core/stages/ci_handler.py`)
- CI fails → Claude diagnoses the logs → posts diagnosis on the PR, alerts Teams
- CI passes → Zoho status → "Validating"

### CLOSURE (`core/stages/closure.py`)
- PR merged → Zoho status → "Fixed"
- Stores the fix in ChromaDB so future similar bugs can learn from it
- Sends Teams feedback card: "Was this fix helpful? 👍 👎"

---

## The Adapters (The Connectors)

Each folder under `adapters/` has one file per provider, all sharing the same interface so they're interchangeable:

```
adapters/llm/            claude.py, openai.py, gemini.py
adapters/issue_tracker/  zoho.py, zoho_tasks.py, jira.py, linear.py
adapters/version_control/ github.py, gitlab.py, azure_devops.py
adapters/notification/   teams.py, slack.py, discord.py
adapters/cloud/          aws.py, gcp.py, azure.py
adapters/vector_store/   chromadb.py, pinecone.py
```

`config/registry.py` reads `settings.yaml` and instantiates the right one for each category. Pipeline stages never import adapters directly — they only use `context["adapters"]["llm"]`, `context["adapters"]["version_control"]`, etc.

---

## Data Models

Three objects flow through the pipeline:

| Model | File | Contains |
|---|---|---|
| `IssueModel` | `core/models/issue.py` | title, description, priority, repos, branch, tenant |
| `FixModel` | `core/models/fix.py` | changed files + new content, reasoning, test, confidence |
| `PRModel` | `core/models/pr.py` | PR title, body, branch, reviewer, Zoho ID, PR URL |

---

## Zoho Task + PRD (Feature Workflow)

When someone creates a **Zoho Projects task** with a PRD document attached:

1. Webhook hits `POST /webhook/zoho/task`
2. Intake downloads the PDF/DOCX and extracts the text (`pdfplumber` for PDFs, `python-docx` for Word docs)
3. PRD content is appended to the issue description
4. `work_type = "feature"` is set throughout the pipeline
5. All prompts shift from *"fix this bug"* to *"implement this feature from the PRD"*
6. PR is titled `[AutoFix] feat: {task title}` and always targets `develop`

---

## Zoho Status Flow

```
Open
 ↓ (issue too vague)       → Needs Clarification
 ↓ (not auto-fixable)      → Needs Manual Review
 ↓ (pipeline started)      → In Progress
 ↓ (PR created)            → Fix Proposed
 ↓ (developer reviewing)   → Under Review
 ↓ (CI running)            → Validating
 ↓ (PR merged)             → Fixed
```

---

## Error Types (`core/exceptions.py`)

**Soft errors** — pipeline stops cleanly, no crash:
- `IssueVagueError` — issue lacks detail
- `NotFixableError` — LLM says not auto-fixable
- `PRTooLargeError` — more than 5 files affected
- `DuplicatePRError` — PR already open for this issue

**Hard errors** — worker catches, sends alert:
- `FixGenerationError` — 3 failed attempts
- `SecurityScanError` — fix failed security review
- `AdapterError` — external service unreachable

---

## Observability

| Component | File | What it tracks |
|---|---|---|
| Logger | `core/observability/logger.py` | `stage_started/completed/failed` events as JSON with issue_id + tenant |
| Metrics | `core/observability/metrics.py` | stage duration, success/fail counts, avg confidence score |
| Tracer | `core/observability/tracer.py` | full trace per issue — each stage is a span with start/end time |

Admin endpoints (`api/admin.py`):

| Endpoint | Purpose |
|---|---|
| `GET /health` | Is the server alive? |
| `GET /metrics` | Pipeline performance stats |
| `GET /queue` | How many jobs are waiting? |
| `GET /pipeline/{trace_id}` | Full trace of one issue run |
| `POST /retry/{issue_id}` | Manually re-trigger a failed job |

---

## How to Run

```bash
cp .env.example .env     # 1. Fill in your API keys
make install             # 2. Install Python dependencies
make setup               # 3. Initialize ChromaDB database
make check               # 4. Test all adapter connections
make run                 # 5. Start webhook server  (terminal 1)
make worker              # 6. Start job processor   (terminal 2)
```

Or with Docker:
```bash
docker-compose up --build
```

---

## File Map

```
api/
  webhook_server.py    ← receives webhooks, enqueues jobs
  admin.py             ← health/metrics/retry endpoints
  middleware.py        ← HMAC signature verification

core/
  pipeline.py          ← orchestrates all 8 stages
  constants.py         ← Zoho status names, branch rules, limits
  exceptions.py        ← error types (soft vs hard)
  models/              ← IssueModel, FixModel, PRModel
  stages/              ← one file per pipeline stage
  queue/               ← producer (enqueue) + worker (dequeue + run)
  observability/       ← logger, metrics, tracer

adapters/              ← one folder per integration category
config/
  registry.py          ← reads settings.yaml, instantiates adapters
  tenants/             ← per-team config overrides

scripts/
  setup_chroma.py      ← run once to init ChromaDB
  test_adapters.py     ← health check all adapters
```
