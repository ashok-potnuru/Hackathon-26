from dataclasses import dataclass


@dataclass
class PRModel:
    title: str
    body: str
    branch_name: str
    base_branch: str
    repo: str
    reviewer: str
    zoho_issue_id: str
    url: str = ""
    number: int = 0
    draft: bool = True
