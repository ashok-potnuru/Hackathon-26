import os

import requests

from adapters.notification.base import NotificationBase
from core.exceptions import AdapterError


class TeamsAdapter(NotificationBase):
    def __init__(self):
        self._url = os.environ["TEAMS_WEBHOOK_URL"]

    def _post(self, payload: dict) -> None:
        requests.post(self._url, json=payload, timeout=10).raise_for_status()

    def send_message(self, channel: str, message: str) -> None:
        self._post({"text": message})

    def send_alert(self, channel: str, message: str) -> None:
        self._post({
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "themeColor": "FF0000",
            "summary": "Alert",
            "sections": [{"activityText": message}],
        })

    def send_feedback_prompt(self, channel: str, issue_id: str) -> None:
        self._post({
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "themeColor": "0076D7",
            "summary": f"Fix feedback — {issue_id}",
            "sections": [{
                "activityTitle": f"Issue {issue_id} has been fixed",
                "activityText": "Was this auto-fix helpful?",
            }],
            "potentialAction": [
                {"@type": "ActionCard", "name": "👍 Yes, it was helpful"},
                {"@type": "ActionCard", "name": "👎 No, needs improvement"},
            ],
        })

    def health_check(self) -> None:
        if not self._url:
            raise AdapterError("TEAMS_WEBHOOK_URL not configured")
