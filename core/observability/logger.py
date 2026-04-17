import json
import logging
import sys
from datetime import datetime


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def log_stage_event(
    logger: logging.Logger,
    event: str,
    stage: str,
    issue_id: str,
    tenant: str = "default",
    **kwargs,
) -> None:
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event": event,
        "stage": stage,
        "issue_id": issue_id,
        "tenant": tenant,
        **kwargs,
    }
    logger.info(json.dumps(entry))
