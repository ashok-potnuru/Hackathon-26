"""
Stage 2: Decides whether an issue is AI-fixable, determines the target branch,
and detects all affected repositories.
Returns an enriched IssueModel or raises NotFixableError if the issue cannot be automated.
Use constants.py for branch rules and priority mapping — do not hard-code values here.
"""
