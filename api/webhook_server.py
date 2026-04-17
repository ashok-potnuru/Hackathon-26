"""
FastAPI application and entry point for all incoming webhooks (Zoho, GitHub CI results).
On receipt: verify the request signature via middleware, push the job to the queue, return HTTP 200.
Never run pipeline logic here — the webhook response must be immediate.
"""
