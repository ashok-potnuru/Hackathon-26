.PHONY: install run worker setup check docker

PYTHON=venv/bin/python
UVICORN=venv/bin/uvicorn

install:
	$(PYTHON) -m pip install -r requirements.txt

run:
	PYTHONPATH=. $(UVICORN) api.webhook_server:app --reload --port 8000

worker:
	PYTHONPATH=. venv/bin/watchfiles "$(PYTHON) -m core.queue.worker" core/ adapters/ config/

check:
	PYTHONPATH=. $(PYTHON) scripts/test_adapters.py

docker:
	docker build -t autofix-ai .
