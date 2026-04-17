import base64
import os

import requests

from adapters.issue_tracker.base import IssueTrackerBase
from core.constants import IssuePriority
from core.exceptions import AdapterError
from core.models.issue import IssueModel

_PRIORITY_MAP = {"highest": IssuePriority.CRITICAL, "high": IssuePriority.HIGH,
                 "medium": IssuePriority.NORMAL, "low": IssuePriority.LOW}


class JiraAdapter(IssueTrackerBase):
    def __init__(self):
        self._base = os.environ["JIRA_BASE_URL"].rstrip("/")
        creds = base64.b64encode(f"{os.environ['JIRA_EMAIL']}:{os.environ['JIRA_API_TOKEN']}".encode()).decode()
        self._headers = {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}

    def get_issue(self, issue_id: str) -> IssueModel:
        resp = requests.get(f"{self._base}/rest/api/3/issue/{issue_id}", headers=self._headers)
        resp.raise_for_status()
        d = resp.json()
        fields = d.get("fields", {})
        prio = _PRIORITY_MAP.get((fields.get("priority") or {}).get("name", "medium").lower(), IssuePriority.NORMAL)
        return IssueModel(
            id=d["id"],
            title=fields.get("summary", ""),
            description=str(fields.get("description") or ""),
            priority=prio,
            zoho_status=str((fields.get("status") or {}).get("name", "Open")),
        )

    def post_comment(self, issue_id: str, message: str) -> None:
        requests.post(
            f"{self._base}/rest/api/3/issue/{issue_id}/comment",
            headers=self._headers,
            json={"body": {"type": "doc", "version": 1, "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": message}]}
            ]}},
        ).raise_for_status()

    def update_status(self, issue_id: str, status: str) -> None:
        resp = requests.get(f"{self._base}/rest/api/3/issue/{issue_id}/transitions", headers=self._headers)
        resp.raise_for_status()
        for t in resp.json().get("transitions", []):
            if t["name"].lower() == status.lower():
                requests.post(
                    f"{self._base}/rest/api/3/issue/{issue_id}/transitions",
                    headers=self._headers,
                    json={"transition": {"id": t["id"]}},
                ).raise_for_status()
                return

    def get_attachments(self, issue_id: str) -> list:
        resp = requests.get(f"{self._base}/rest/api/3/issue/{issue_id}", headers=self._headers)
        resp.raise_for_status()
        return [a.get("content", "") for a in resp.json().get("fields", {}).get("attachment", [])]

    def health_check(self) -> None:
        try:
            requests.get(f"{self._base}/rest/api/3/myself", headers=self._headers).raise_for_status()
        except Exception as e:
            raise AdapterError(f"Jira health check failed: {e}")
