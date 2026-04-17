import os

import requests

from adapters.issue_tracker.base import IssueTrackerBase
from core.constants import IssuePriority
from core.exceptions import AdapterError
from core.models.issue import IssueModel

_TOKEN_URL = "https://accounts.zoho.com/oauth/v2/token"
_API_BASE = "https://desk.zoho.com/api/v1"
_PRIORITY_MAP = {"high": IssuePriority.HIGH, "low": IssuePriority.LOW, "medium": IssuePriority.NORMAL}


class ZohoAdapter(IssueTrackerBase):
    def __init__(self):
        self._client_id = os.environ["ZOHO_CLIENT_ID"]
        self._client_secret = os.environ["ZOHO_CLIENT_SECRET"]
        self._refresh_token = os.environ["ZOHO_REFRESH_TOKEN"]
        self._org_id = os.environ["ZOHO_ORG_ID"]
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
        return {"Authorization": f"Zoho-oauthtoken {self._token()}", "orgId": self._org_id}

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        resp = requests.request(method, f"{_API_BASE}{path}", headers=self._headers(), **kwargs)
        if resp.status_code == 401:
            self._access_token = None
            resp = requests.request(method, f"{_API_BASE}{path}", headers=self._headers(), **kwargs)
        resp.raise_for_status()
        return resp

    def get_issue(self, issue_id: str) -> IssueModel:
        data = self._request("GET", f"/tickets/{issue_id}").json()
        return IssueModel(
            id=str(data["id"]),
            title=data.get("subject", ""),
            description=data.get("description", ""),
            priority=_PRIORITY_MAP.get(data.get("priority", "medium").lower(), IssuePriority.NORMAL),
            zoho_status=data.get("status", "Open"),
        )

    def post_comment(self, issue_id: str, message: str) -> None:
        self._request("POST", f"/tickets/{issue_id}/comments",
                      json={"content": message, "isPublic": False},
                      headers={**self._headers(), "Content-Type": "application/json"})

    def update_status(self, issue_id: str, status: str) -> None:
        self._request("PATCH", f"/tickets/{issue_id}",
                      json={"status": status},
                      headers={**self._headers(), "Content-Type": "application/json"})

    def get_attachments(self, issue_id: str) -> list:
        data = self._request("GET", f"/tickets/{issue_id}/attachments").json()
        return [a.get("href", "") for a in data.get("data", [])]

    def health_check(self) -> None:
        try:
            self._token()
        except Exception as e:
            raise AdapterError(f"Zoho health check failed: {e}")
