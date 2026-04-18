.PHONY: install run worker check docker deploy-local

PYTHON=venv/bin/python
UVICORN=venv/bin/uvicorn

install:
	$(PYTHON) -m pip install -r requirements.txt

# Local dev
run:
	PYTHONPATH=. $(UVICORN) api.webhook_server:app --reload --port 8000

worker:
	PYTHONPATH=. venv/bin/watchfiles "$(PYTHON) -m core.queue.worker" core/ adapters/ config/

check:
	PYTHONPATH=. $(PYTHON) scripts/test_adapters.py

# Docker (for EC2)
docker:
	docker build -t autofix-ai .

deploy-local:
	ECR_IMAGE=autofix-ai:latest docker compose up -d
