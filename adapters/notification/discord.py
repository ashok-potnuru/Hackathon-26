import os

import requests

from adapters.notification.base import NotificationBase
from core.exceptions import AdapterError


class DiscordAdapter(NotificationBase):
    def __init__(self):
        self._url = os.environ["DISCORD_WEBHOOK_URL"]

    def _post(self, payload: dict) -> None:
        requests.post(self._url, json=payload, timeout=10).raise_for_status()

    def send_message(self, channel: str, message: str) -> None:
        self._post({"content": message})

    def send_alert(self, channel: str, message: str) -> None:
        self._post({"embeds": [{"title": "Alert", "description": message, "color": 16711680}]})

    def send_feedback_prompt(self, channel: str, issue_id: str) -> None:
        self._post({"content": f"Issue `{issue_id}` fixed! React with 👍 or 👎 to give feedback."})

    def health_check(self) -> None:
        if not self._url:
            raise AdapterError("DISCORD_WEBHOOK_URL not configured")
