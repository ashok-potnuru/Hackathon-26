"""
Test triggering AWS CodePipeline manually.
Usage:
    python scripts/test_trigger_pipeline.py --pipeline MY_PIPELINE_NAME
    python scripts/test_trigger_pipeline.py --pipeline MY_PIPELINE_NAME --branch master
"""

import argparse
import os
import sys
import time

import boto3
from dotenv import load_dotenv

load_dotenv()


def change_branch(pipeline_name: str, branch: str) -> None:
    region = os.environ.get("AWS_REGION", "us-east-1")
    client = boto3.client("codepipeline", region_name=region)

    print(f"Fetching pipeline config: {pipeline_name}")
    r = client.get_pipeline(name=pipeline_name)
    pipeline = r["pipeline"]
    pipeline.pop("version", None)

    # Update branch in all source actions
    changed = False
    for stage in pipeline.get("stages", []):
        for action in stage.get("actions", []):
            cfg = action.get("configuration", {})
            if "BranchName" in cfg:
                print(f"  Changing branch: {cfg['BranchName']} → {branch}")
                cfg["BranchName"] = branch
                changed = True

    if not changed:
        print("  WARNING — No BranchName found in source actions.")
        return

    client.update_pipeline(pipeline=pipeline)
    print(f"  Pipeline updated to branch: {branch}")


TERMINAL_STATES = {"Succeeded", "Failed", "Stopped", "Superseded"}


def poll_status(pipeline_name: str, execution_id: str, interval: int = 15) -> str:
    region = os.environ.get("AWS_REGION", "us-east-1")
    client = boto3.client("codepipeline", region_name=region)

    print(f"\nPolling pipeline status (every {interval}s) ...")
    while True:
        try:
            r = client.get_pipeline_execution(
                pipelineName=pipeline_name,
                pipelineExecutionId=execution_id,
            )
            ex = r["pipelineExecution"]
            status = ex["status"]
            print(f"  [{time.strftime('%H:%M:%S')}] status: {status}")
            if status in TERMINAL_STATES:
                print(f"\nPipeline {status}: executionId={execution_id}")
                return status
        except Exception as e:
            print(f"  ERROR — {e}")
            return "Error"
        time.sleep(interval)


def trigger(pipeline_name: str, issue_id: str = "TEST-001") -> str | None:
    region = os.environ.get("AWS_REGION", "us-east-1")
    client = boto3.client("codepipeline", region_name=region)

    print(f"Triggering pipeline: {pipeline_name} (region={region})")
    try:
        r = client.start_pipeline_execution(
            name=pipeline_name,
            variables=[{"name": "issue_id", "value": issue_id}],
        )
        execution_id = r["pipelineExecutionId"]
        print(f"  SUCCESS — executionId: {execution_id}")
        return execution_id
    except client.exceptions.PipelineNotFoundException:
        print(f"  ERROR — Pipeline '{pipeline_name}' not found in {region}")
        sys.exit(1)
    except Exception as e:
        print(f"  ERROR — {e}")
        sys.exit(1)


def _get_pipeline_branch(client, pipeline_name: str) -> str | None:
    """Read BranchName from the pipeline's source action configuration."""
    try:
        r = client.get_pipeline(name=pipeline_name)
        for stage in r["pipeline"].get("stages", []):
            for action in stage.get("actions", []):
                cfg = action.get("configuration", {})
                if "BranchName" in cfg:
                    return cfg["BranchName"]
    except Exception:
        pass
    return None


def _extract_revision(client, pipeline_name: str, execution_id: str) -> tuple[str | None, str | None]:
    """Return (branch, commit_id) for a given execution ID."""
    detail = client.get_pipeline_execution(
        pipelineName=pipeline_name,
        pipelineExecutionId=execution_id,
    )
    artifacts = detail["pipelineExecution"].get("artifactRevisions", [])
    branch, commit_id = None, None
    for artifact in artifacts:
        revision_url = artifact.get("revisionUrl", "")
        commit_id = artifact.get("revisionId")

        # Try parsing branch from revisionUrl query string
        if "branch=" in revision_url:
            branch = revision_url.split("branch=")[-1].split("&")[0]

        # Try parsing branch from revisionSummary (e.g. "refs/heads/main @ abc123")
        if not branch:
            summary = artifact.get("revisionSummary", "")
            if "refs/heads/" in summary:
                branch = summary.split("refs/heads/")[-1].split(" ")[0].split("\n")[0]

        break  # first artifact is the source

    # Fall back to reading branch from pipeline config
    if not branch:
        branch = _get_pipeline_branch(client, pipeline_name)

    return branch, commit_id


def get_old_release_info(pipeline_name: str) -> dict:
    """Return branch name and commit ID from the last Succeeded and last Failed executions."""
    region = os.environ.get("AWS_REGION", "us-east-1")
    client = boto3.client("codepipeline", region_name=region)

    print(f"\nFetching old release info for: {pipeline_name}")
    try:
        r = client.list_pipeline_executions(pipelineName=pipeline_name, maxResults=20)
        executions = r.get("pipelineExecutionSummaries", [])

        last_success = next((ex for ex in executions if ex.get("status") == "Succeeded"), None)
        last_failed = next((ex for ex in executions if ex.get("status") == "Failed"), None)

        result = {}

        for label, ex in [("Succeeded", last_success), ("Failed", last_failed)]:
            print(f"\n  --- Last {label} ---")
            if not ex:
                print(f"  No {label} execution found.")
                continue
            eid = ex["pipelineExecutionId"]
            print(f"  executionId : {eid}")
            print(f"  started     : {ex.get('startTime')}")
            branch, commit_id = _extract_revision(client, pipeline_name, eid)
            print(f"  Branch      : {branch}")
            print(f"  Commit ID   : {commit_id}")
            result[label.lower()] = {"execution_id": eid, "branch": branch, "commit_id": commit_id}

        return result

    except Exception as e:
        print(f"  ERROR — {e}")
        return {}


def check_status(pipeline_name: str) -> None:
    region = os.environ.get("AWS_REGION", "us-east-1")
    client = boto3.client("codepipeline", region_name=region)

    print(f"\nLatest execution status for: {pipeline_name}")
    try:
        r = client.list_pipeline_executions(pipelineName=pipeline_name, maxResults=1)
        execs = r.get("pipelineExecutionSummaries", [])
        if not execs:
            print("  No executions found.")
            return
        ex = execs[0]
        print(f"  executionId : {ex['pipelineExecutionId']}")
        print(f"  status      : {ex['status']}")
        print(f"  started     : {ex['startTime']}")
    except Exception as e:
        print(f"  ERROR — {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline", required=True, help="CodePipeline pipeline name")
    parser.add_argument("--branch", default=None, help="Switch pipeline source branch before triggering")
    parser.add_argument("--issue-id", default="TEST-001", help="issue_id variable passed to pipeline")
    parser.add_argument("--status-only", action="store_true", help="Only check status, don't trigger")
    parser.add_argument("--old-release", action="store_true", help="Show branch and commit ID from last successful execution")
    parser.add_argument("--poll-interval", type=int, default=15, help="Seconds between status polls")
    args = parser.parse_args()

    if args.old_release:
        get_old_release_info(args.pipeline)
        sys.exit(0)

    if args.branch:
        change_branch(args.pipeline, args.branch)

    if args.status_only:
        check_status(args.pipeline)
    else:
        execution_id = trigger(args.pipeline, args.issue_id)
        if execution_id:
            final_status = poll_status(args.pipeline, execution_id, args.poll_interval)
            sys.exit(0 if final_status == "Succeeded" else 1)
