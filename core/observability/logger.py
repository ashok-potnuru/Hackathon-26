"""
Structured logger used by all pipeline stages; implement structured log emission here.
Emits stage_started, stage_completed, and stage_failed events carrying issue_id and stage name.
All log entries must include tenant and issue_id fields for end-to-end traceability.
"""
