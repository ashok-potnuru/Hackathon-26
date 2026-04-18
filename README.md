# AutoFix AI

Automatically fixes bugs from Zoho Desk issues, raises a Draft PR on GitHub, and notifies Microsoft Teams — with mandatory developer review and CI before merge.

## Architecture

8-stage pipeline: Intake → Triage → Research → Fix Generation → PR Creation → Developer Review → CI/CD → Closure

All integrations (LLM, issue tracker, VCS, notifications, cloud, vector store) are swappable via `settings.yaml`.

## Quick Start

```bash
cp .env.example .env        # fill in your credentials
make install                # install deps + pre-commit hooks
make setup                  # seed ChromaDB
make check                  # verify all adapter connections
make run                    # start webhook server
```

Or with Docker:

```bash
docker-compose up --build
```

## Project Structure

```
core/          Pure business logic — 8 pipeline stages, models, queue, observability
adapters/      Pluggable integrations — one folder per category
config/        settings.yaml + per-tenant configs + adapter registry
api/           FastAPI webhook server + admin endpoints
scripts/       Setup and health check utilities
tests/         Unit and integration tests
```

## Configuration

Edit `settings.yaml` to pick your LLM and model — no code changes needed:

```yaml
llm: openai          # claude | openai | gemini
model: gpt-4o        # model name for the active provider
```

| Provider | Example models |
|----------|---------------|
| `openai` | `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo` |
| `claude` | `claude-sonnet-4-6`, `claude-opus-4-7` |
| `gemini` | `gemini-1.5-pro` |

## Test Files

### Unit tests — no API key needed, run instantly

| File | What it tests |
|------|--------------|
| `tests/test_agents.py` | PlannerAgent, CoderAgent, ReviewerAgent — all mocked |
| `tests/test_orchestrator.py` | MultiAgentOrchestrator full loop — mocked adapters |
| `tests/test_graph_navigator.py` | GraphNavigator keyword search and BFS — offline |

### Individual agent tests — test one agent at a time with real LLM

| File | Agent | What it does |
|------|-------|-------------|
| `scripts/test_planner.py` | PlannerAgent | Extracts keywords from issue → searches graph → returns files to fix |
| `scripts/test_explorer.py` | ExplorerAgent | Reads code → decides which files must change vs. context only |
| `scripts/test_coder.py` | CoderAgent | Generates the actual code fix for given files |
| `scripts/test_reviewer.py` | ReviewerAgent | Reviews a fix → returns PASS / FAIL / PARTIAL + detailed checks |

### Other live tests

| File | What it tests |
|------|--------------|
| `scripts/test_agents_live.py` | All agents end-to-end in one run |
| `scripts/test_adapters.py` | All configured adapters (Zoho, GitHub, etc.) can connect |
| `tests/test_github_adapter.py` | GitHub adapter — fetches files, creates PRs |

## Running Tests

### Step 1 — do this once per terminal session

```bash
source venv/bin/activate          # activate the virtual environment
set -a && source .env && set +a   # load API keys from .env
pip install pyyaml -q             # only needed once if not already installed
```

### Step 2 — run whichever test you want

```bash
# Unit tests (no API key needed)
make test
pytest tests/test_agents.py -v
pytest tests/test_orchestrator.py -v
pytest tests/test_graph_navigator.py -v

# Test each AI agent individually (calls real OpenAI/Claude API)
python3 scripts/test_planner.py    # PlannerAgent
python3 scripts/test_explorer.py   # ExplorerAgent
python3 scripts/test_coder.py      # CoderAgent
python3 scripts/test_reviewer.py   # ReviewerAgent

# All agents in one run
python3 scripts/test_agents_live.py

# Verify all adapter connections (needs all env vars in .env)
make check
```

### To test a different bug — edit 2 lines at the top of any script

```python
ISSUE_TITLE       = "Your bug title here"
ISSUE_DESCRIPTION = "What goes wrong and where..."
```

### To switch model — edit `settings.yaml`

```yaml
llm: openai
model: gpt-4o-mini   # cheaper/faster for quick tests
```

## Adding a New Adapter

See [CONTRIBUTING.md](CONTRIBUTING.md).
