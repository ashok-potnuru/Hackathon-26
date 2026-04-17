.PHONY: install run test lint format setup check

install:
	pip install -r requirements.txt
	pre-commit install

run:
	uvicorn api.webhook_server:app --reload --port 8000

worker:
	python -m core.queue.worker

test:
	pytest tests/ -v

lint:
	ruff check .
	mypy .

format:
	black .
	ruff check --fix .

setup:
	python scripts/setup_chroma.py

check:
	python scripts/test_adapters.py

docker-up:
	docker-compose up --build

docker-down:
	docker-compose down
