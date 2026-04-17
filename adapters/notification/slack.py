import os

import requests

from adapters.notification.base import NotificationBase
from core.exceptions import AdapterError

_API = "https://slack.com/api"


class SlackAdapter(NotificationBase):
    def __init__(self):
        self._token = os.environ.get("SLACK_BOT_TOKEN", "")
        self._webhook = os.environ.get("SLACK_WEBHOOK_URL", "")

    def _send(self, channel: str, text: str) -> None:
        if self._webhook:
            requests.post(self._webhook, json={"text": text}, timeout=10).raise_for_status()
        elif self._token:
            requests.post(
                f"{_API}/chat.postMessage",
                headers={"Authorization": f"Bearer {self._token}"},
                json={"channel": channel or "#general", "text": text},
                timeout=10,
            ).raise_for_status()
        else:
            raise AdapterError("Slack not configured: set SLACK_BOT_TOKEN or SLACK_WEBHOOK_URL")

    def send_message(self, channel: str, message: str) -> None:
        self._send(channel, message)

    def send_alert(self, channel: str, message: str) -> None:
        self._send(channel, f":warning: *ALERT*: {message}")

    def send_feedback_prompt(self, channel: str, issue_id: str) -> None:
        self._send(channel, f"Issue `{issue_id}` fixed. Was this helpful? React with :thumbsup: or :thumbsdown:")

    def health_check(self) -> None:
        if not self._token and not self._webhook:
            raise AdapterError("Slack not configured: set SLACK_BOT_TOKEN or SLACK_WEBHOOK_URL")
