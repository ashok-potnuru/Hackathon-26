"""
Stage 6: Handles developer review comments on an open PR — parses requested changes,
generates updated fixes, and pushes new commits addressing the feedback.
Re-notifies Teams after each round of changes and updates Zoho status to Under Review.
Never interact with VCS or notifications directly — use injected adapter interfaces.
"""
