import os

import requests

from adapters.issue_tracker.base import IssueTrackerBase
from core.exceptions import AdapterError
from core.models.issue import IssueModel

_API_URL = "https://api.linear.app/graphql"


class LinearAdapter(IssueTrackerBase):
    def __init__(self):
        self._headers = {"Authorization": os.environ["LINEAR_API_KEY"], "Content-Type": "application/json"}

    def _q(self, query: str, variables: dict = None) -> dict:
        resp = requests.post(_API_URL, headers=self._headers, json={"query": query, "variables": variables or {}})
        resp.raise_for_status()
        return resp.json().get("data", {})

    def get_issue(self, issue_id: str) -> IssueModel:
        data = self._q(
            "query($id:String!){issue(id:$id){id title description priority state{name}}}",
            {"id": issue_id},
        )
        d = data.get("issue", {})
        return IssueModel(
            id=d.get("id", issue_id),
            title=d.get("title", ""),
            description=d.get("description", ""),
            priority=str(d.get("priority", 3)),
            zoho_status=d.get("state", {}).get("name", "Open"),
        )

    def post_comment(self, issue_id: str, message: str) -> None:
        self._q(
            "mutation($id:String!,$body:String!){commentCreate(input:{issueId:$id,body:$body}){success}}",
            {"id": issue_id, "body": message},
        )

    def update_status(self, issue_id: str, status: str) -> None:
        self.post_comment(issue_id, f"Status updated to: {status}")

    def get_attachments(self, issue_id: str) -> list:
        data = self._q(
            "query($id:String!){issue(id:$id){attachments{nodes{url}}}}",
            {"id": issue_id},
        )
        return [a.get("url", "") for a in data.get("issue", {}).get("attachments", {}).get("nodes", [])]

    def health_check(self) -> None:
        try:
            self._q("query{viewer{id}}")
        except Exception as e:
            raise AdapterError(f"Linear health check failed: {e}")
