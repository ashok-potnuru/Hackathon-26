from dataclasses import dataclass, field
from typing import List


@dataclass
class IssueModel:
    id: str
    title: str
    description: str
    attachments: List[str] = field(default_factory=list)
    priority: str = "normal"
    affected_repos: List[str] = field(default_factory=list)
    target_branch: str = "develop"
    zoho_status: str = "Open"
    tenant: str = "default"
