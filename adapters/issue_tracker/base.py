from abc import ABC, abstractmethod
from typing import List

from core.models.issue import IssueModel


class IssueTrackerBase(ABC):
    @abstractmethod
    def get_issue(self, issue_id: str) -> IssueModel: ...

    @abstractmethod
    def post_comment(self, issue_id: str, message: str) -> None: ...

    @abstractmethod
    def update_status(self, issue_id: str, status: str) -> None: ...

    @abstractmethod
    def get_attachments(self, issue_id: str) -> List[str]: ...

    @abstractmethod
    def health_check(self) -> None: ...
