"""
Admin API endpoints for monitoring and manual intervention in the pipeline.
Implement: GET /health, GET /pipeline/{id}, GET /queue, POST /retry/{job_id}.
Used by operators to inspect pipeline state and manually retry failed jobs.
"""
