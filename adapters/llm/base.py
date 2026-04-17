from abc import ABC, abstractmethod
from typing import List


class LLMBase(ABC):
    @abstractmethod
    def analyze(self, prompt: str) -> str: ...

    @abstractmethod
    def generate_fix(self, context: dict) -> str: ...

    @abstractmethod
    def review_fix(self, fix: str) -> dict: ...

    @abstractmethod
    def embed(self, text: str) -> List[float]: ...

    @abstractmethod
    def health_check(self) -> None: ...
