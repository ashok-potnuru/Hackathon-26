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