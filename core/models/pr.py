from dataclasses import dataclass, field
from typing import List


@dataclass
class PRModel:
    title: str
    body: str
    branch_name: str
    base_branch: str
    repo: str
    reviewer: str
    zoho_issue_id: str
    related_prs: List[str] = field(default_factory=list)
    url: str = ""
    number: int = 0
    draft: bool = True
