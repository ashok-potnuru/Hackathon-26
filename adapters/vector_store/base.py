from abc import ABC, abstractmethod
from typing import Dict, List


class VectorStoreBase(ABC):
    @abstractmethod
    def store_fix(self, issue_id: str, issue_text: str, fix_text: str) -> None: ...

    @abstractmethod
    def search_similar(self, issue_text: str, top_k: int = 5) -> List[Dict]: ...

    @abstractmethod
    def health_check(self) -> None: ...
