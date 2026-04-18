# AutoFix AI

Autonomous issue-to-deployment pipeline. A Zoho Sprints ticket comes in, a 5-agent AI system writes the fix, a Draft PR is raised on GitHub, the team approves in Microsoft Teams with one click, and AWS CodePipeline deploys it — zero manual coding.

## How It Works

```
Zoho Sprints Issue
       ↓  (webhook)
   Webhook Server  ──►  AWS SQS  ──►  Worker
       ↓
   INTAKE — quality gate (FIXABLE or VAGUE?)
       ↓
   FIX GENERATION — 5-agent pipeline
       │  MetaPlanner  → which repos? (api / cms / both)
       │  Planner      → keyword search on code graph → target files
       │  Explorer     → fetch files, classify must-change vs context
       │  Coder        → generate surgical edits (old → new)
       │  Reviewer     → adversarial review (7 checks)
       ↓
   GitHub Draft PR created
       ↓
   Teams card — View PR | Approve & Deploy | Reject
       ↓  (click Approve after merging PR)
   AWS CodePipeline triggered
       ↓
   Teams green card — "✅ Deployment Started"
```

---

## Prerequisites

- Python 3.11+
- Docker + Docker Compose
- Accounts / credentials for:
  - OpenAI (or Anthropic / Google Gemini)
  - Zoho Sprints (OAuth2)
  - GitHub (Personal Access Token)
  - Microsoft Teams (Incoming Webhook URL)
  - AWS (SQS queue + CodePipeline)

---

## Setup

### 1. Clone and create `.env`

```bash
git clone <repo-url>
cd hackathon
cp .env.example .env   # then fill in all values (see below)
```

### 2. `.env` reference

```env
# LLM
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...   # only if using Claude

# Zoho Sprints
ZOHO_CLIENT_ID=...
ZOHO_CLIENT_SECRET=...
ZOHO_REFRESH_TOKEN=...
ZOHO_SPRINTS_TEAM_ID=...          # numeric team ID from Zoho URL
ZOHO_SPRINTS_WEBHOOK_TOKEN=...    # secret token for webhook HMAC verification

# GitHub
GITHUB_TOKEN=ghp_...

# Microsoft Teams
TEAMS_WEBHOOK_URL=https://tv2zdev.webhook.office.com/webhookb2/...
BASE_URL=http://localhost:8000    # public URL of this server (used in Teams buttons)

# AWS
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
AWS_SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/...
AWS_S3_BUCKET=...
AWS_CODEPIPELINE_NAME=wtdev2api-jobs
```

### 3. `settings.yaml` — pick your LLM and repos

```yaml
llm: openai          # claude | openai | gemini
model: gpt-4o-mini   # model name for the active provider

default_repos:
  api: org/repo-api
  cms: org/repo-cms
default_branch: SIT  # branch PRs are raised against
```

| Provider | Recommended model |
|----------|------------------|
| `openai` | `gpt-4o-mini` (higher rate limits) or `gpt-4o` |
| `claude` | `claude-sonnet-4-6` |
| `gemini` | `gemini-1.5-pro` |

---

## Running

### Docker (recommended)

```bash
docker compose up --build
```

This starts two containers:
| Container | Role |
|-----------|------|
| `webhook` | FastAPI server on port 8000 — receives Zoho webhooks and approval clicks |
| `worker`  | Polls SQS, runs the pipeline for each job |

### Local (without Docker)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Terminal 1 — webhook server
PYTHONPATH=. uvicorn api.webhook_server:app --reload --port 8000

# Terminal 2 — worker
PYTHONPATH=. python -m core.queue.worker
```

---

## Zoho Webhook Setup

1. Go to **Zoho Sprints → Settings → Webhooks → Add Webhook**
2. URL: `https://<your-server>/webhook/zoho`
3. Events: `Item Create`, `Item Update`
4. Secret token: same value as `ZOHO_SPRINTS_WEBHOOK_TOKEN` in `.env`

The server also accepts `POST /` for generic testing.

---

## Teams Setup

1. In your Teams channel → **Connectors → Incoming Webhook → Configure**
2. Give it a name (e.g. "AutoFix AI"), copy the webhook URL
3. Paste it into `.env` as `TEAMS_WEBHOOK_URL`
4. Set `BASE_URL` to the public URL of your server (so Teams buttons point to it)

> If running locally, `BASE_URL=http://localhost:8000` works — buttons open in your browser which can reach localhost.

---

## Approval Flow

When a PR is raised, a Teams card appears with three buttons:

| Button | Action |
|--------|--------|
| **View PR** | Opens the GitHub PR in browser |
| **Approve & Deploy** | Triggers AWS CodePipeline, posts green status card |
| **Reject** | Posts red status card, no deployment |

The server deduplicates clicks — double-clicking Approve only fires one deploy job.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check |
| `POST` | `/webhook/zoho` | Zoho Sprints webhook receiver |
| `POST` | `/api/approvals` | JSON approval (for programmatic use) |
| `GET` | `/api/approvals/confirm` | Browser approval from Teams button click |

### Manual trigger (testing)

```bash
curl -X POST http://localhost:8000/webhook/zoho \
  -H "Content-Type: application/json" \
  -H "X-ZOHO-WEBHOOK-TOKEN: <your-token>" \
  -d '{
    "triggerEvent": "Item_CREATE",
    "zoid": "<team_id>",
    "itemId": "12345",
    "projectId": "proj-1",
    "sprintId": "sprint-1",
    "data": "{\"ItemName\": \"Fix null email crash\", \"ItemDescription\": \"Auth middleware crashes when user.email is null\"}"
  }'
```

### Manual approve (testing)

```bash
curl -X POST http://localhost:8000/api/approvals \
  -H "Content-Type: application/json" \
  -d '{"action": "approved", "issue_id": "12345", "branch": "SIT", "title": "Fix null email"}'
```

---

## Pipeline Stages

### INTAKE
- Extracts title + description from webhook payload (no Zoho API round-trip)
- Downloads and parses PDF/DOCX attachments for PRD content
- LLM quality gate: `FIXABLE` → continue, `VAGUE` → post Zoho comment + stop

### FIX GENERATION (5 agents)
| Agent | Job |
|-------|-----|
| MetaPlanner | Decides which repos need changes and in what order |
| Planner | Searches code graph (Louvain community detection) to find target files |
| Explorer | Fetches files from GitHub, classifies must-change vs context-only |
| Coder | Generates surgical `old_string → new_string` edits, never rewrites whole files |
| Reviewer | Adversarial review: Correctness, Security, Regression, Boundaries, Error Handling, Concurrency, Style |

### DEPLOY
- Triggered by Teams approval
- Updates CodePipeline source branch to `SIT`
- Starts execution, returns `executionId`
- Posts green "Deployment Started" card to Teams

---

## Worker Behavior

- Polls SQS every 5 seconds
- On success: deletes message from queue
- On soft error (`IssueVagueError`, `NotFixableError`): alerts Teams, deletes message (no retry)
- On hard error: retries up to **3 times**, then deletes message and alerts Teams

---

## Project Structure

```
api/                  FastAPI webhook server and approval endpoints
adapters/
  cloud/              AWS (SQS, S3, CodePipeline)
  issue_tracker/      Zoho Sprints
  llm/                OpenAI / Claude / Gemini
  notification/       Microsoft Teams
  version_control/    GitHub
config/               Adapter registry, settings loader
core/
  agents/             MetaPlanner, Planner, Explorer, Coder, Reviewer
  models/             IssueModel, PRModel, CoderResult, etc.
  pipeline.py         Stage orchestration
  queue/              SQS producer + worker loop
  stages/             intake.py, agent_runner.py, deployer.py
  utils/              GraphNavigator (code graph search)
scripts/              Test and trigger utilities
graph_api/            Pre-built code graph for API repo
graph_cms/            Pre-built code graph for CMS repo
settings.yaml         LLM + repo + branch configuration
docker-compose.yml    Webhook + worker services
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `410 Gone` on Teams webhook | Regenerate the incoming webhook URL in Teams channel settings |
| `404` on GitHub branch create | Check `default_branch` in `settings.yaml` matches actual repo branch |
| `AWS_CODEPIPELINE_NAME not set` | Add `AWS_CODEPIPELINE_NAME=<name>` to `.env`, restart containers |
| OpenAI `rate_limit_exceeded` | Switch to `gpt-4o-mini` in `settings.yaml` (higher TPM quota) |
| Worker retrying same job | Hard error hit — check logs, fix root cause, purge SQS if needed: `docker compose exec worker python3 -c "import boto3,os; boto3.client('sqs',region_name=os.environ['AWS_REGION']).purge_queue(QueueUrl=os.environ['AWS_SQS_QUEUE_URL'])"` |
| PR raises against wrong branch | Set `default_branch: SIT` (or your branch) in `settings.yaml` |
| Teams buttons not showing | Ensure `TEAMS_WEBHOOK_URL` is not expired; regenerate if needed |
