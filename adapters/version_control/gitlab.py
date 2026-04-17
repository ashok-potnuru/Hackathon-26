import base64
import os

import requests

from adapters.version_control.base import VersionControlBase
from core.exceptions import AdapterError
from core.models.pr import PRModel


class GitLabAdapter(VersionControlBase):
    def __init__(self):
        self._token = os.environ["GITLAB_TOKEN"]
        base = os.environ.get("GITLAB_URL", "https://gitlab.com").rstrip("/")
        self._api = f"{base}/api/v4"
        self._h = {"PRIVATE-TOKEN": self._token}

    def _enc(self, repo: str) -> str:
        return requests.utils.quote(repo, safe="")

    def get_file(self, repo: str, path: str, branch: str = "main") -> str:
        r = requests.get(
            f"{self._api}/projects/{self._enc(repo)}/repository/files/{requests.utils.quote(path, safe='')}",
            headers=self._h, params={"ref": branch},
        )
        r.raise_for_status()
        return base64.b64decode(r.json()["content"]).decode()

    def list_files(self, repo: str, branch: str = "main") -> list:
        r = requests.get(
            f"{self._api}/projects/{self._enc(repo)}/repository/tree",
            headers=self._h, params={"ref": branch, "recursive": True, "per_page": 100},
        )
        r.raise_for_status()
        return [i["path"] for i in r.json() if i["type"] == "blob"]

    def create_branch(self, repo: str, name: str, base: str) -> None:
        requests.post(
            f"{self._api}/projects/{self._enc(repo)}/repository/branches",
            headers=self._h, json={"branch": name, "ref": base},
        ).raise_for_status()

    def commit_changes(self, repo: str, branch: str, files: dict, message: str) -> None:
        actions = [{"action": "update", "file_path": p, "content": c} for p, c in files.items()]
        requests.post(
            f"{self._api}/projects/{self._enc(repo)}/repository/commits",
            headers=self._h,
            json={"branch": branch, "commit_message": message, "actions": actions},
        ).raise_for_status()

    def create_pr(self, pr: PRModel) -> PRModel:
        r = requests.post(
            f"{self._api}/projects/{self._enc(pr.repo)}/merge_requests",
            headers=self._h,
            json={"source_branch": pr.branch_name, "target_branch": pr.base_branch,
                  "title": pr.title, "description": pr.body, "draft": pr.draft},
        )
        r.raise_for_status()
        pr.url = r.json().get("web_url", "")
        pr.number = r.json().get("iid", 0)
        return pr

    def get_blame(self, repo: str, file_path: str) -> dict:
        r = requests.get(
            f"{self._api}/projects/{self._enc(repo)}/repository/files/{requests.utils.quote(file_path, safe='')}/blame",
            headers=self._h, params={"ref": "main"},
        )
        if r.ok and r.json():
            c = r.json()[0].get("commit", {})
            return {"author": c.get("author_name", ""), "login": c.get("author_email", "").split("@")[0]}
        return {}

    def get_open_prs(self, repo: str) -> list:
        r = requests.get(
            f"{self._api}/projects/{self._enc(repo)}/merge_requests",
            headers=self._h, params={"state": "opened"},
        )
        r.raise_for_status()
        return r.json()

    def health_check(self) -> None:
        try:
            requests.get(f"{self._api}/user", headers=self._h).raise_for_status()
        except Exception as e:
            raise AdapterError(f"GitLab health check failed: {e}")
