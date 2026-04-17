import base64
import os

import requests

from adapters.version_control.base import VersionControlBase
from core.exceptions import AdapterError
from core.models.pr import PRModel


class AzureDevOpsAdapter(VersionControlBase):
    def __init__(self):
        org = os.environ["AZURE_DEVOPS_ORG"]
        project = os.environ["AZURE_DEVOPS_PROJECT"]
        pat = os.environ["AZURE_DEVOPS_PAT"]
        creds = base64.b64encode(f":{pat}".encode()).decode()
        self._h = {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}
        self._api = f"https://dev.azure.com/{org}/{project}/_apis"

    def get_file(self, repo: str, path: str, branch: str = "main") -> str:
        r = requests.get(
            f"{self._api}/git/repositories/{repo}/items",
            headers=self._h,
            params={"path": path, "versionDescriptor.version": branch, "api-version": "7.0"},
        )
        r.raise_for_status()
        return r.text

    def list_files(self, repo: str, branch: str = "main") -> list:
        r = requests.get(
            f"{self._api}/git/repositories/{repo}/items",
            headers=self._h,
            params={"recursionLevel": "Full", "versionDescriptor.version": branch, "api-version": "7.0"},
        )
        r.raise_for_status()
        return [i["path"].lstrip("/") for i in r.json().get("value", []) if not i.get("isFolder")]

    def create_branch(self, repo: str, name: str, base: str) -> None:
        r = requests.get(
            f"{self._api}/git/repositories/{repo}/refs",
            headers=self._h, params={"filter": f"heads/{base}", "api-version": "7.0"},
        )
        r.raise_for_status()
        sha = r.json()["value"][0]["objectId"]
        requests.post(
            f"{self._api}/git/repositories/{repo}/refs?api-version=7.0",
            headers=self._h,
            json=[{"name": f"refs/heads/{name}", "newObjectId": sha, "oldObjectId": "0" * 40}],
        ).raise_for_status()

    def commit_changes(self, repo: str, branch: str, files: dict, message: str) -> None:
        changes = [
            {"changeType": "edit", "item": {"path": f"/{p}"},
             "newContent": {"content": c, "contentType": "rawtext"}}
            for p, c in files.items()
        ]
        requests.post(
            f"{self._api}/git/repositories/{repo}/pushes?api-version=7.0",
            headers=self._h,
            json={"refUpdates": [{"name": f"refs/heads/{branch}"}],
                  "commits": [{"comment": message, "changes": changes}]},
        ).raise_for_status()

    def create_pr(self, pr: PRModel) -> PRModel:
        r = requests.post(
            f"{self._api}/git/repositories/{pr.repo}/pullrequests?api-version=7.0",
            headers=self._h,
            json={"sourceRefName": f"refs/heads/{pr.branch_name}",
                  "targetRefName": f"refs/heads/{pr.base_branch}",
                  "title": pr.title, "description": pr.body, "isDraft": pr.draft},
        )
        r.raise_for_status()
        pr.url = r.json().get("url", "")
        pr.number = r.json().get("pullRequestId", 0)
        return pr

    def get_blame(self, repo: str, file_path: str) -> dict:
        return {}

    def get_open_prs(self, repo: str) -> list:
        r = requests.get(
            f"{self._api}/git/repositories/{repo}/pullrequests",
            headers=self._h, params={"status": "active", "api-version": "7.0"},
        )
        r.raise_for_status()
        return r.json().get("value", [])

    def health_check(self) -> None:
        try:
            org = self._api.split("dev.azure.com/")[1].split("/")[0]
            requests.get(f"https://dev.azure.com/{org}/_apis/projects?api-version=7.0", headers=self._h).raise_for_status()
        except Exception as e:
            raise AdapterError(f"Azure DevOps health check failed: {e}")
