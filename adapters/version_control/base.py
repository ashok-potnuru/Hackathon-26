from abc import ABC, abstractmethod
from typing import Dict, List

from core.models.pr import PRModel


class VersionControlBase(ABC):
    @abstractmethod
    def get_file(self, repo: str, path: str, branch: str = "main") -> str: ...

    @abstractmethod
    def list_files(self, repo: str, branch: str = "main") -> List[str]: ...

    @abstractmethod
    def create_branch(self, repo: str, name: str, base: str) -> None: ...

    @abstractmethod
    def commit_changes(self, repo: str, branch: str, files: Dict[str, str], message: str) -> None: ...

    @abstractmethod
    def create_pr(self, pr: PRModel) -> PRModel: ...

    @abstractmethod
    def get_blame(self, repo: str, file_path: str) -> Dict[str, str]: ...

    @abstractmethod
    def get_open_prs(self, repo: str) -> List[dict]: ...

    @abstractmethod
    def health_check(self) -> None: ...
