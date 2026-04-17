"""
Abstract base class that all issue tracker adapters must implement.
Methods to implement: get_issue(issue_id), post_comment(issue_id, message),
update_status(issue_id, status), get_attachments(issue_id).
To add a new tracker: subclass this class and implement all 4 methods.
"""
