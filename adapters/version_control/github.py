import base64
import os

import requests

from adapters.version_control.base import VersionControlBase
from core.exceptions import AdapterError
from core.models.pr import PRModel

_API = "https://api.github.com"


class GitHubAdapter(VersionControlBase):
    def __init__(self):
        token = os.environ["GITHUB_TOKEN"]
        self._h = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _get(self, url: str, **kw) -> dict:
        r = requests.get(url, headers=self._h, **kw)
        r.raise_for_status()
        return r.json()

    def _post(self, url: str, data: dict) -> dict:
        r = requests.post(url, headers=self._h, json=data)
        r.raise_for_status()
        return r.json()

    def _put(self, url: str, data: dict) -> dict:
        r = requests.put(url, headers=self._h, json=data)
        r.raise_for_status()
        return r.json()

    def get_file(self, repo: str, path: str, branch: str = "main") -> str:
        data = self._get(f"{_API}/repos/{repo}/contents/{path}", params={"ref": branch})
        return base64.b64decode(data["content"]).decode()

    def list_files(self, repo: str, branch: str = "main") -> list:
        tree = self._get(f"{_API}/repos/{repo}/git/trees/{branch}", params={"recursive": "1"})
        return [i["path"] for i in tree.get("tree", []) if i["type"] == "blob"]

    def create_branch(self, repo: str, name: str, base: str) -> None:
        sha = self._get(f"{_API}/repos/{repo}/git/ref/heads/{base}")["object"]["sha"]
        self._post(f"{_API}/repos/{repo}/git/refs", {"ref": f"refs/heads/{name}", "sha": sha})

    def commit_changes(self, repo: str, branch: str, files: dict, message: str) -> None:
        for path, content in files.items():
            sha = None
            try:
                sha = self._get(f"{_API}/repos/{repo}/contents/{path}", params={"ref": branch})["sha"]
            except Exception:
                pass
            payload = {"message": message, "content": base64.b64encode(content.encode()).decode(), "branch": branch}
            if sha:
                payload["sha"] = sha
            self._put(f"{_API}/repos/{repo}/contents/{path}", payload)

    def create_pr(self, pr: PRModel) -> PRModel:
        data = self._post(f"{_API}/repos/{pr.repo}/pulls", {
            "title": pr.title, "body": pr.body,
            "head": pr.branch_name, "base": pr.base_branch, "draft": pr.draft,
        })
        pr.url = data["html_url"]
        pr.number = data["number"]
        if pr.reviewer:
            try:
                requests.post(
                    f"{_API}/repos/{pr.repo}/pulls/{pr.number}/requested_reviewers",
                    headers=self._h, json={"reviewers": [pr.reviewer]},
                )
            except Exception:
                pass
        return pr

    def get_blame(self, repo: str, file_path: str) -> dict:
        commits = self._get(f"{_API}/repos/{repo}/commits", params={"path": file_path, "per_page": 3})
        if not commits:
            return {}
        top = commits[0]
        return {
            "author": top.get("commit", {}).get("author", {}).get("name", ""),
            "login": (top.get("author") or {}).get("login", ""),
        }

    def get_open_prs(self, repo: str) -> list:
        return self._get(f"{_API}/repos/{repo}/pulls", params={"state": "open"})

    def health_check(self) -> None:
        try:
            self._get(f"{_API}/user")
        except Exception as e:
            raise AdapterError(f"GitHub health check failed: {e}")
