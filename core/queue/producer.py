from config.registry import load_adapters


def enqueue_job(payload: dict) -> str:
    adapters = load_adapters()
    return adapters["cloud"].queue_job(payload)
