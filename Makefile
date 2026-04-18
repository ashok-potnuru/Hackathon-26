.PHONY: install run test lint format setup check

PYTHON=venv/bin/python
UVICORN=venv/bin/uvicorn

install:
	$(PYTHON) -m pip install -r requirements.txt
	pre-commit install

run:
	PYTHONPATH=. $(UVICORN) api.webhook_server:app --reload --port 8000

worker:
	PYTHONPATH=. venv/bin/watchfiles "$(PYTHON) -m core.queue.worker" core/ adapters/ config/

test:
	PYTHONPATH=. venv/bin/pytest tests/ -v

lint:
	venv/bin/ruff check .
	venv/bin/mypy .

format:
	venv/bin/black .
	venv/bin/ruff check --fix .

setup:
	PYTHONPATH=. $(PYTHON) scripts/setup_chroma.py

check:
	PYTHONPATH=. $(PYTHON) scripts/test_adapters.py

docker-up:
	docker-compose up --build

docker-down:
	docker-compose down
