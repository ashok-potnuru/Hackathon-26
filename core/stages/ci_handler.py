"""
Stage 7: Receives the CI result webhook and handles both pass and fail outcomes.
On failure, Claude analyzes the CI logs, posts a diagnosis comment on the PR,
and notifies Teams with details.
Updates Zoho status to Validating regardless of outcome.
"""
