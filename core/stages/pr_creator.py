"""
Stage 5: Builds the full PR payload — branch name, title, body (root cause, impact,
rollback instructions, Zoho link) — and auto-assigns a reviewer via git blame.
Handles both single-repo and cross-repo scenarios (multiple linked PRs).
Returns a PRModel; never push to VCS directly here.
"""
