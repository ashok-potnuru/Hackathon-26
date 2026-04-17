"""
Defines IssueModel, the core data contract for an issue flowing through the pipeline.
Fields: id, title, description, attachments, priority, affected_repos, target_branch,
zoho_status, tenant. Used by all stages — never add adapter-specific fields here.
"""
