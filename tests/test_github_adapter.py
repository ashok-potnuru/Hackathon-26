"""
Manual test script for GitHubAdapter.
Run: set -a && source .env && set +a && python -m tests.test_github_adapter

Required env vars:
  GITHUB_TOKEN=ghp_...
  TEST_REPO=owner/repo-name   (a repo you own)
"""

import os
import time

from adapters.version_control.github import GitHubAdapter
from core.models.pr import PRModel

REPO = os.environ.get("TEST_REPO", "")


def test_health_check():
    adapter = GitHubAdapter()
    adapter.health_check()
    print("[PASS] health_check — connected to GitHub")


def test_list_files():
    adapter = GitHubAdapter()
    files = adapter.list_files(REPO)
    print(f"[PASS] list_files — found {len(files)} files")
    for f in files[:5]:
        print(f"       {f}")
    return files


def test_get_file(files: list):
    if not files:
        print("[SKIP] get_file — no files found")
        return
    adapter = GitHubAdapter()
    content = adapter.get_file(REPO, files[0])
    print(f"[PASS] get_file — {files[0]} ({len(content)} chars)")


def test_create_branch():
    adapter = GitHubAdapter()
    branch_name = f"autofix/test-{int(time.time())}"
    adapter.create_branch(REPO, branch_name, "main")
    print(f"[PASS] create_branch — {branch_name}")
    return branch_name


def test_commit_changes(branch_name: str):
    adapter = GitHubAdapter()
    files = {"autofix_test.txt": f"test file created at {time.time()}\n"}
    adapter.commit_changes(REPO, branch_name, files, "chore: autofix test commit")
    print(f"[PASS] commit_changes — pushed autofix_test.txt to {branch_name}")


def test_create_pr(branch_name: str):
    adapter = GitHubAdapter()
    pr = PRModel(
        title="[AutoFix] Test PR",
        body="This is a test draft PR created by the AutoFix adapter.",
        branch_name=branch_name,
        base_branch="main",
        repo=REPO,
        reviewer="",
        zoho_issue_id="",
        draft=True,
    )
    result = adapter.create_pr(pr)
    print(f"[PASS] create_pr — {result.url}")


def test_get_blame(files: list):
    if not files:
        print("[SKIP] get_blame — no files found")
        return
    adapter = GitHubAdapter()
    blame = adapter.get_blame(REPO, files[0])
    print(f"[PASS] get_blame — {blame}")


if __name__ == "__main__":
    if not REPO:
        print("ERROR: set TEST_REPO=owner/repo-name")
        raise SystemExit(1)

    print(f"\nTesting GitHubAdapter against: {REPO}\n")

    test_health_check()
    files = test_list_files()
    test_get_file(files)
    branch = test_create_branch()
    test_commit_changes(branch)
    test_create_pr(branch)
    test_get_blame(files)

    print("\nAll tests passed.")
