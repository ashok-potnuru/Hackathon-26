import os

import requests

from adapters.issue_tracker.base import IssueTrackerBase
from core.constants import IssuePriority
from core.exceptions import AdapterError
from core.models.issue import IssueModel

_TOKEN_URL = "https://accounts.zoho.com/oauth/v2/token"
_API_BASE = "https://sprintsapi.zoho.com/zsapi"

_PRIORITY_MAP = {
    "high": IssuePriority.HIGH,
    "medium": IssuePriority.NORMAL,
    "low": IssuePriority.LOW,
}

# composite ID format: "{teamId}|{itemId}"
_SEP = "|"


def encode_item_id(team_id: str, item_id: str) -> str:
    return f"{team_id}{_SEP}{item_id}"


def _split_id(composite_id: str) -> tuple[str, str]:
    parts = composite_id.split(_SEP, 1)
    return (parts[0], parts[1]) if len(parts) == 2 else ("", composite_id)


class ZohoSprintsAdapter(IssueTrackerBase):
    def __init__(self):
        self._client_id = os.environ["ZOHO_CLIENT_ID"]
        self._client_secret = os.environ["ZOHO_CLIENT_SECRET"]
        self._refresh_token = os.environ["ZOHO_REFRESH_TOKEN"]
        self._team_id = os.environ["ZOHO_SPRINTS_TEAM_ID"]
        self._access_token: str | None = None

    # ── auth ──────────────────────────────────────────────────────────────

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
        url = f"{_API_BASE}/team/{self._team_id}{path}"
        resp = requests.request(method, url, headers=self._headers(), **kwargs)
        if resp.status_code == 401:
            self._access_token = None
            resp = requests.request(method, url, headers=self._headers(), **kwargs)
        resp.raise_for_status()
        return resp

    # ── IssueTrackerBase ───────────────────────────────────────────────────

    def get_issue(self, composite_id: str) -> IssueModel:
        _, item_id = _split_id(composite_id)
        data = self._request("GET", f"/item/{item_id}/").json()

        item = data.get("item", [{}])
        item = item[0] if isinstance(item, list) and item else item

        prio = _PRIORITY_MAP.get(str(item.get("priority", "medium")).lower(), IssuePriority.NORMAL)
        item_type = str(item.get("typeName", "issue")).lower()  # "issue" or "task"

        return IssueModel(
            id=composite_id,
            title=item.get("name", ""),
            description=item.get("description", ""),
            priority=prio,
            zoho_status=item.get("statusName", "Open"),
            tenant=item_type,   # "issue" → bugfix, "task" → feature in intake
        )

    def post_comment(self, composite_id: str, message: str) -> None:
        _, item_id = _split_id(composite_id)
        self._request("POST", f"/item/{item_id}/notes/", json={"content": message})

    def update_status(self, composite_id: str, status: str) -> None:
        _, item_id = _split_id(composite_id)
        self._request("PUT", f"/item/{item_id}/", json={"statusName": status})

    def get_attachments(self, composite_id: str) -> list:
        _, item_id = _split_id(composite_id)
        data = self._request("GET", f"/item/{item_id}/attachment/").json()
        files = data.get("attachment", data.get("files", []))
        return [
            {
                "url": f.get("downloadUrl", f.get("url", "")),
                "filename": f.get("fileName", f.get("filename", "")),
                "id": f.get("attachmentId", f.get("id", "")),
            }
            for f in files
        ]

    def download_attachment(self, url: str) -> bytes:
        resp = requests.get(url, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        return resp.content

    # ── Sprints-specific ───────────────────────────────────────────────────

    def get_sprint_items(self, sprint_id: str) -> list[IssueModel]:
        """Fetch all issues and tasks from a sprint."""
        data = self._request("GET", f"/sprints/{sprint_id}/item/").json()
        result = []
        for item in data.get("item", []):
            item_id = str(item.get("itemId", ""))
            composite_id = encode_item_id(self._team_id, item_id)
            prio = _PRIORITY_MAP.get(str(item.get("priority", "medium")).lower(), IssuePriority.NORMAL)
            result.append(IssueModel(
                id=composite_id,
                title=item.get("name", ""),
                description=item.get("description", ""),
                priority=prio,
                zoho_status=item.get("statusName", "Open"),
                tenant=str(item.get("typeName", "issue")).lower(),
            ))
        return result

    def health_check(self) -> None:
        try:
            self._request("GET", "/sprints/")
        except Exception as e:
            raise AdapterError(f"ZohoSprints health check failed: {e}")
