"""
Defines PRModel, which represents a pull request to be created via the VCS adapter.
Fields: title, body, branch_name, base_branch, repo, reviewer, zoho_issue_id,
related_prs (for cross-repo). Passed from pr_creator to the version_control adapter.
"""
