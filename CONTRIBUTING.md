# Contributing

## Adding a New Adapter

1. Pick the adapter category (e.g. `adapters/notification/`)
2. Copy an existing implementation (e.g. `teams.py`) as a reference
3. Implement every method defined in `base.py` — no skipping
4. Register it in `config/registry.py`
5. Add the provider name to `settings.yaml` comments
6. Add a test in `tests/integration/`

## Adding a New Pipeline Stage

1. Create the file in `core/stages/`
2. Accept and return core models (`IssueModel`, `FixModel`, `PRModel`)
3. Never import from `adapters/` directly — use injected adapter interfaces
4. Wire it into `core/pipeline.py`
5. Add unit tests in `tests/unit/`

## Code Style

- Line length: 100
- Formatter: black
- Linter: ruff
- Type hints required on all public functions

Run before committing:

```bash
make format
make lint
make test
```

Pre-commit hooks run automatically on `git commit`.

## Branch Naming

```
feature/short-description
fix/short-description
adapter/provider-name
```

## Pull Request

Fill in the PR template. Link the relevant issue. All CI checks must pass before requesting review.
