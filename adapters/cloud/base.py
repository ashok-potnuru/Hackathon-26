from abc import ABC, abstractmethod
from typing import Dict, Optional


class CloudBase(ABC):
    @abstractmethod
    def store_file(self, key: str, data: bytes) -> None: ...

    @abstractmethod
    def read_file(self, key: str) -> bytes: ...

    @abstractmethod
    def queue_job(self, payload: Dict) -> str: ...

    @abstractmethod
    def dequeue_job(self) -> Optional[Dict]: ...

    @abstractmethod
    def delete_job(self, receipt_handle: str) -> None: ...

    @abstractmethod
    def get_secret(self, name: str) -> str: ...

    @abstractmethod
    def health_check(self) -> None: ...
