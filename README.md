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

## Configuration

Edit `settings.yaml` to choose providers:

```yaml
llm: claude                 # claude | openai | gemini
issue_tracker: zoho         # zoho | jira | linear
version_control: github     # github | gitlab | azure_devops
notification: teams         # teams | slack | discord
cloud: aws                  # aws | gcp | azure
vector_store: chromadb      # chromadb | pinecone
```

For per-team config, copy `config/tenants/example.yaml` and fill in team-specific values.

## Project Structure

```
core/          Pure business logic — 8 pipeline stages, models, queue, observability
adapters/      Pluggable integrations — one folder per category
config/        settings.yaml + per-tenant configs + adapter registry
api/           FastAPI webhook server + admin endpoints
scripts/       Setup and health check utilities
tests/         Unit and integration tests
```

## Running Tests

```bash
make test
```

## Adding a New Adapter

See [CONTRIBUTING.md](CONTRIBUTING.md).
