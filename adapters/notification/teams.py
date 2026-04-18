import json
import requests
import os
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL")
BASE_URL    = os.getenv("BASE_URL", "http://localhost:8000")


# ──────────────────────────────────────────────
# Simple messages
# ──────────────────────────────────────────────

def send_simple_message(text: str):
    _post({"text": text})
    print("✉️  Simple message sent")


def send_rich_card(title: str, message: str, color: str = "0076D7"):
    _post({
        "@type":      "MessageCard",
        "@context":   "http://schema.org/extensions",
        "themeColor": color,
        "summary":    title,
        "sections": [{
            "activityTitle": title,
            "activityText":  message,
            "facts": [
                {"name": "Source", "value": "EC2 Instance"},
                {"name": "Time",   "value": _now()},
            ]
        }]
    })
    print(f"📋  Rich card sent: {title}")


def send_alert(message: str):
    send_rich_card(title="ALERT", message=message, color="FF0000")


def send_success(message: str):
    send_rich_card(title="Success", message=message, color="00C853")

# ──────────────────────────────────────────────
# Deployment Approval card
# All deployment fields shown on the card AND
# sent in the POST body when Approve / Deny clicked
# ──────────────────────────────────────────────

def send_deployment_approval(
    request_id:  str,
    app_type:    str,   # "cms" | "api" | "frontend" etc.
    branch:      str,   # e.g. "main", "release/v3.0"
    version:     str,   # e.g. "3.0.1"
    environment: str,   # "production" | "staging" | "dev"
    service:     str,   # e.g. "payment-api", "cms-service"
    region:      str,   # e.g. "us-east-1"
    triggered_by: str,  # who triggered the deployment
    commit_id:   str = "",   # git commit hash
    description: str = "",   # extra notes
):
    """
    Send a deployment approval card to Teams.

    All fields are shown on the card as facts AND sent in the
    POST body to your server when Approve or Deny is clicked.
    Your server can then use these fields to trigger the AWS deployment.
    """
    endpoint = f"{BASE_URL}/api/approvals"

    # All deployment info bundled into one dict
    deployment_info = {
        "request_id":   request_id,
        "app_type":     app_type,
        "branch":       branch,
        "version":      version,
        "environment":  environment,
        "service":      service,
        "region":       region,
        "triggered_by": triggered_by,
        "commit_id":    commit_id,
        "description":  description,
        "timestamp":    _now(),
    }

    approve_body = json.dumps({**deployment_info, "action": "approved"})
    deny_body    = json.dumps({**deployment_info, "action": "denied"})

    _post({
        "@type":      "MessageCard",
        "@context":   "http://schema.org/extensions",
        "themeColor": "0076D7",
        "summary":    f"Deployment Approval — {service}",
        "sections": [{
            "activityTitle":    "🚀 Deployment Approval Required",
            "activitySubtitle": f"{service}  •  {environment}",
            "activityText":     description or f"Please approve or deny the deployment of {service} to {environment}.",
            "facts": [
                {"name": "Request ID",   "value": request_id},
                {"name": "App Type",     "value": app_type},
                {"name": "Service",      "value": service},
                {"name": "Branch",       "value": branch},
                {"name": "Version",      "value": version},
                {"name": "Environment",  "value": environment},
                {"name": "Region",       "value": region},
                {"name": "Triggered By", "value": triggered_by},
                {"name": "Commit ID",    "value": commit_id or "N/A"},
                {"name": "Time",         "value": _now()},
            ]
        }],
        "potentialAction": [
            {
                "@type":  "HttpPOST",
                "name":   "✅ Approve",
                "target": endpoint,
                "body":   approve_body,
                "headers": [{"name": "Content-Type", "value": "application/json"}]
            },
            {
                "@type":  "HttpPOST",
                "name":   "❌ Deny",
                "target": endpoint,
                "body":   deny_body,
                "headers": [{"name": "Content-Type", "value": "application/json"}]
            }
        ]
    })
    print(f"🚀  Deployment approval card sent  →  {endpoint}")

def send_pr_approval(
    request_id:  str,
    app_type:    str,   # "cms" | "api" | "frontend" etc.
    branch:      str,   # e.g. "main", "release/v3.0"
    version:     str,   # e.g. "3.0.1"
    environment: str,   # "production" | "staging" | "dev"
    service:     str,   # e.g. "payment-api", "cms-service"
    region:      str,   # e.g. "us-east-1"
    triggered_by: str,  # who triggered the deployment
    commit_id:   str = "",   # git commit hash
    description: str = "",   # extra notes
):
    """
    Send a deployment approval card to Teams.

    All fields are shown on the card as facts AND sent in the
    POST body to your server when Approve or Deny is clicked.
    Your server can then use these fields to trigger the AWS deployment.
    """
    endpoint = f"{BASE_URL}/api/approvals"

    # All deployment info bundled into one dict
    deployment_info = {
        "request_id":   request_id,
        "app_type":     app_type,
        "branch":       branch,
        "version":      version,
        "environment":  environment,
        "service":      service,
        "region":       region,
        "triggered_by": triggered_by,
        "commit_id":    commit_id,
        "description":  description,
        "timestamp":    _now(),
    }

    approve_body = json.dumps({**deployment_info, "action": "approved"})
    deny_body    = json.dumps({**deployment_info, "action": "denied"})

    _post({
        "@type":      "MessageCard",
        "@context":   "http://schema.org/extensions",
        "themeColor": "0076D7",
        "summary":    f"Deployment Approval — {service}",
        "sections": [{
            "activityTitle":    "🚀 Deployment Approval Required",
            "activitySubtitle": f"{service}  •  {environment}",
            "activityText":     description or f"Please approve or deny the deployment of {service} to {environment}.",
            "facts": [
                {"name": "Request ID",   "value": request_id},
                {"name": "App Type",     "value": app_type},
                {"name": "Service",      "value": service},
                {"name": "Branch",       "value": branch},
                {"name": "Version",      "value": version},
                {"name": "Environment",  "value": environment},
                {"name": "Region",       "value": region},
                {"name": "Triggered By", "value": triggered_by},
                {"name": "Commit ID",    "value": commit_id or "N/A"},
                {"name": "Time",         "value": _now()},
            ]
        }],
        "potentialAction": [
            {
                "@type":  "HttpPOST",
                "name":   "✅ Approve PR",
                "target": endpoint,
                "body":   approve_body,
                "headers": [{"name": "Content-Type", "value": "application/json"}]
            },
            {
                "@type":  "HttpPOST",
                "name":   "❌ Deny PR",
                "target": endpoint,
                "body":   deny_body,
                "headers": [{"name": "Content-Type", "value": "application/json"}]
            }
        ]
    })
    print(f"🚀  Deployment approval card sent  →  {endpoint}")
# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _post(payload: dict):
    resp = requests.post(WEBHOOK_URL, json=payload, timeout=10)
    resp.raise_for_status()


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ──────────────────────────────────────────────
# Smoke test
# ──────────────────────────────────────────────

def notify_pr_raised(issue_id: str, title: str, pr_url: str, branch: str, base_branch: str = "master", extra_pr_urls: list = None):
    import urllib.parse
    base = f"{BASE_URL}/api/approvals/confirm"
    params = urllib.parse.urlencode({
        "issue_id": issue_id,
        "title": title,
        "pr_url": pr_url,
        "branch": base_branch,
    })
    approve_url = f"{base}?action=approved&{params}"
    deny_url = f"{base}?action=denied&{params}"

    facts = [
        {"name": "Issue ID", "value": issue_id},
        {"name": "Branch", "value": branch},
        {"name": "Deploy To", "value": base_branch},
        {"name": "PR (api)", "value": pr_url},
    ]
    actions = [{"@type": "OpenUri", "name": "View PR (api)", "targets": [{"os": "default", "uri": pr_url}]}]

    for repo_type, url in (extra_pr_urls or []):
        facts.append({"name": f"PR ({repo_type})", "value": url})
        actions.append({"@type": "OpenUri", "name": f"View PR ({repo_type})", "targets": [{"os": "default", "uri": url}]})

    facts.append({"name": "Time", "value": _now()})
    actions += [
        {"@type": "OpenUri", "name": "Approve & Deploy", "targets": [{"os": "default", "uri": approve_url}]},
        {"@type": "OpenUri", "name": "Reject", "targets": [{"os": "default", "uri": deny_url}]},
    ]

    _post({
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "0076D7",
        "summary": f"AutoFix PR Ready — {title}",
        "sections": [{
            "activityTitle": "AutoFix PR Raised",
            "activitySubtitle": title,
            "activityText": "Review and merge the PR(s) on GitHub, then click Approve & Deploy.",
            "facts": facts,
        }],
        "potentialAction": actions,
    })
    print(f"PR notification sent -> {pr_url}")


def notify_deployment_status(issue_id: str, title: str, pr_url: str, action: str):
    approved = action == "approved"
    color = "00C853" if approved else "FF5252"
    status = "Approved & Deployed" if approved else "Rejected"
    icon = "✅" if approved else "❌"

    _post({
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": color,
        "summary": f"AutoFix {status} — {title}",
        "sections": [{
            "activityTitle": f"{icon} {status}",
            "activitySubtitle": title,
            "facts": [
                {"name": "Issue ID", "value": issue_id},
                {"name": "PR", "value": pr_url or "N/A"},
                {"name": "Time", "value": _now()},
            ]
        }]
    })


class TeamsAdapter:
    def send_message(self, _channel: str, text: str):
        send_simple_message(text)

    def send_simple_message(self, text: str):
        send_simple_message(text)

    def send_rich_card(self, title: str, message: str, color: str = "0076D7"):
        send_rich_card(title, message, color)

    def send_alert(self, _channel: str, message: str):
        send_alert(message)

    def send_success(self, message: str):
        send_success(message)

    def send_deployment_approval(self, **kwargs):
        send_deployment_approval(**kwargs)

    def send_pr_approval(self, **kwargs):
        send_pr_approval(**kwargs)

    def notify_pr_raised(self, issue_id: str, title: str, pr_url: str, branch: str, base_branch: str = "master", extra_pr_urls: list = None):
        notify_pr_raised(issue_id, title, pr_url, branch, base_branch, extra_pr_urls)

    def notify_deployment_status(self, issue_id: str, title: str, pr_url: str, action: str):
        notify_deployment_status(issue_id, title, pr_url, action)


if __name__ == "__main__":

    # print("Test 1: plain message")
    # send_simple_message("Hello from local machine!")

    # print("Test 2: alert")
    # send_alert("CPU usage exceeded 90% on EC2 instance!")

    # print("Test 3: success")
    # send_success("Deployment completed successfully!")

    # Test 4 — full deployment approval card
    print("Test 4: deployment approval card")
    send_deployment_approval(
        request_id=   "req-20240101-001",
        app_type=     "api",                # cms | api | frontend
        branch=       "release/v3.0",
        version=      "3.0.1",
        environment=  "production",
        service=      "payment-api",
        region=       "us-east-1",
        triggered_by= "lakshmi",
        commit_id=    "a1b2c3d4",
        description=  "Deploying payment-api v3.0.1 with new checkout flow",
    )