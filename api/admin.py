from fastapi import FastAPI

from core.observability.metrics import metrics
from core.observability.tracer import tracer
from core.queue.worker import get_queue_depth

admin_app = FastAPI(title="AutoFix AI Admin")


@admin_app.get("/health")
def health():
    return {"status": "ok"}


@admin_app.get("/metrics")
def get_metrics():
    return metrics.get_summary()


@admin_app.get("/queue")
def queue_status():
    return {"depth": get_queue_depth()}


@admin_app.get("/pipeline/{trace_id}")
def get_pipeline(trace_id: str):
    spans = tracer.get_trace(trace_id)
    if not spans:
        return {"error": "trace not found"}
    return {"trace_id": trace_id, "spans": spans}


@admin_app.post("/retry/{issue_id}")
def retry_job(issue_id: str):
    from core.queue.producer import enqueue_job
    msg_id = enqueue_job({"issue_id": issue_id, "source": "zoho", "tenant": "default"})
    return {"status": "queued", "message_id": msg_id}
