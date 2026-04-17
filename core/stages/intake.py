"""
Stage 1: Receives the raw webhook payload, runs multimodal analysis (text + attachments),
and validates issue quality before the pipeline proceeds.
Returns an IssueModel on success or raises IssueVagueError if the issue lacks sufficient detail.
Never import from adapters/ directly — use the injected llm and issue_tracker adapter interfaces.
"""
