import os

import yaml

from core.exceptions import AdapterNotConfiguredError


def _load_settings() -> dict:
    path = os.path.join(os.path.dirname(__file__), "..", "settings.yaml")
    with open(path) as f:
        return yaml.safe_load(f)


def load_adapters() -> dict:
    s = _load_settings()
    adapters: dict = {}

    llm = s.get("llm", "claude")
    if llm == "claude":
        from adapters.llm.claude import ClaudeAdapter
        adapters["llm"] = ClaudeAdapter()
    elif llm == "openai":
        from adapters.llm.openai import OpenAIAdapter
        adapters["llm"] = OpenAIAdapter()
    elif llm == "gemini":
        from adapters.llm.gemini import GeminiAdapter
        adapters["llm"] = GeminiAdapter()
    else:
        raise AdapterNotConfiguredError(f"Unknown llm: {llm}")

    tracker = s.get("issue_tracker", "zoho")
    if tracker == "zoho":
        from adapters.issue_tracker.zoho import ZohoAdapter
        adapters["issue_tracker"] = ZohoAdapter()
    elif tracker == "jira":
        from adapters.issue_tracker.jira import JiraAdapter
        adapters["issue_tracker"] = JiraAdapter()
    elif tracker == "linear":
        from adapters.issue_tracker.linear import LinearAdapter
        adapters["issue_tracker"] = LinearAdapter()
    else:
        raise AdapterNotConfiguredError(f"Unknown issue_tracker: {tracker}")

    vc = s.get("version_control", "github")
    if vc == "github":
        from adapters.version_control.github import GitHubAdapter
        adapters["version_control"] = GitHubAdapter()
    elif vc == "gitlab":
        from adapters.version_control.gitlab import GitLabAdapter
        adapters["version_control"] = GitLabAdapter()
    elif vc == "azure_devops":
        from adapters.version_control.azure_devops import AzureDevOpsAdapter
        adapters["version_control"] = AzureDevOpsAdapter()
    else:
        raise AdapterNotConfiguredError(f"Unknown version_control: {vc}")

    notif = s.get("notification", "teams")
    if notif == "teams":
        from adapters.notification.teams import TeamsAdapter
        adapters["notification"] = TeamsAdapter()
    elif notif == "slack":
        from adapters.notification.slack import SlackAdapter
        adapters["notification"] = SlackAdapter()
    elif notif == "discord":
        from adapters.notification.discord import DiscordAdapter
        adapters["notification"] = DiscordAdapter()
    else:
        raise AdapterNotConfiguredError(f"Unknown notification: {notif}")

    cloud = s.get("cloud", "aws")
    if cloud == "aws":
        from adapters.cloud.aws import AWSAdapter
        adapters["cloud"] = AWSAdapter()
    elif cloud == "gcp":
        from adapters.cloud.gcp import GCPAdapter
        adapters["cloud"] = GCPAdapter()
    elif cloud == "azure":
        from adapters.cloud.azure import AzureCloudAdapter
        adapters["cloud"] = AzureCloudAdapter()
    else:
        raise AdapterNotConfiguredError(f"Unknown cloud: {cloud}")

    vs = s.get("vector_store", "chromadb")
    if vs == "chromadb":
        from adapters.vector_store.chromadb import ChromaDBAdapter
        adapters["vector_store"] = ChromaDBAdapter()
    elif vs == "pinecone":
        from adapters.vector_store.pinecone import PineconeAdapter
        adapters["vector_store"] = PineconeAdapter()
    else:
        raise AdapterNotConfiguredError(f"Unknown vector_store: {vs}")

    return adapters
