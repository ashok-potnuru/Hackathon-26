from abc import ABC, abstractmethod


class NotificationBase(ABC):
    @abstractmethod
    def send_message(self, channel: str, message: str) -> None: ...

    @abstractmethod
    def send_alert(self, channel: str, message: str) -> None: ...

    @abstractmethod
    def send_feedback_prompt(self, channel: str, issue_id: str) -> None: ...

    @abstractmethod
    def health_check(self) -> None: ...
