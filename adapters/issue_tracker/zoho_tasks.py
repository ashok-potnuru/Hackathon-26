import os

import requests

from adapters.issue_tracker.base import IssueTrackerBase
from core.constants import IssuePriority
from core.exceptions import AdapterError
from core.models.issue import IssueModel

_TOKEN_URL = "https://accounts.zoho.com/oauth/v2/token"
_API_BASE = "https://projectsapi.zoho.com/restapi"
_PRIORITY_MAP = {"high": IssuePriority.HIGH, "low": IssuePriority.LOW, "medium": IssuePriority.NORMAL}

# composite ID format: "{project_id}|{task_id}"
_SEP = "|"


def _split_id(composite_id: str) -> tuple[str, str]:
    parts = composite_id.split(_SEP, 1)
    return (parts[0], parts[1]) if len(parts) == 2 else ("", composite_id)


def encode_task_id(project_id: str, task_id: str) -> str:
    return f"{project_id}{_SEP}{task_id}"


class ZohoTasksAdapter(IssueTrackerBase):
    def __init__(self):
        self._client_id = os.environ["ZOHO_CLIENT_ID"]
        self._client_secret = os.environ["ZOHO_CLIENT_SECRET"]
        self._refresh_token = os.environ["ZOHO_REFRESH_TOKEN"]
        self._portal_id = os.environ["ZOHO_PORTAL_ID"]
        self._access_token: str | None = None

    def _token(self) -> str:
        if self._access_token:
            return self._access_token
        resp = requests.post(_TOKEN_URL, params={
            "refresh_token": self._refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "refresh_token",
        })
        resp.raise_for_status()
        self._access_token = resp.json()["access_token"]
        return self._access_token

    def _headers(self) -> dict:
        return {"Authorization": f"Zoho-oauthtoken {self._token()}"}

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        resp = requests.request(method, f"{_API_BASE}/portal/{self._portal_id}{path}",
                                headers=self._headers(), **kwargs)
        if resp.status_code == 401:
            self._access_token = None
            resp = requests.request(method, f"{_API_BASE}/portal/{self._portal_id}{path}",
                                    headers=self._headers(), **kwargs)
        resp.raise_for_status()
        return resp

    def get_issue(self, composite_id: str) -> IssueModel:
        project_id, task_id = _split_id(composite_id)
        data = self._request("GET", f"/projects/{project_id}/tasks/{task_id}/").json()
        task = data.get("tasks", [{}])[0] if isinstance(data.get("tasks"), list) else data
        prio = _PRIORITY_MAP.get(str(task.get("priority", "medium")).lower(), IssuePriority.NORMAL)
        return IssueModel(
            id=composite_id,
            title=task.get("name", ""),
            description=task.get("description", ""),
            priority=prio,
            zoho_status=task.get("status", {}).get("name", "Open") if isinstance(task.get("status"), dict) else str(task.get("status", "Open")),
        )

    def post_comment(self, composite_id: str, message: str) -> None:
        project_id, task_id = _split_id(composite_id)
        self._request("POST", f"/projects/{project_id}/tasks/{task_id}/comments/",
                      json={"content": message})

    def update_status(self, composite_id: str, status: str) -> None:
        project_id, task_id = _split_id(composite_id)
        self._request("PUT", f"/projects/{project_id}/tasks/{task_id}/",
                      json={"status": status})

    def get_attachments(self, composite_id: str) -> list:
        project_id, task_id = _split_id(composite_id)
        data = self._request("GET", f"/projects/{project_id}/tasks/{task_id}/attachments/").json()
        return [
            {"url": f.get("content_url", ""), "filename": f.get("filename", ""), "id": f.get("id", "")}
            for f in data.get("files", [])
        ]

    def download_attachment(self, url: str) -> bytes:
        resp = requests.get(url, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        return resp.content

    def health_check(self) -> None:
        try:
            self._token()
        except Exception as e:
            raise AdapterError(f"ZohoTasks health check failed: {e}")
