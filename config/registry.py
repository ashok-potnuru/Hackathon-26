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

    llm = s.get("llm", "openai")
    model = s.get("model")
    if llm == "claude":
        from adapters.llm.claude import ClaudeAdapter
        adapters["llm"] = ClaudeAdapter(model=model)
    elif llm == "openai":
        from adapters.llm.openai import OpenAIAdapter
        adapters["llm"] = OpenAIAdapter(model=model)
    elif llm == "gemini":
        from adapters.llm.gemini import GeminiAdapter
        adapters["llm"] = GeminiAdapter()
    else:
        raise AdapterNotConfiguredError(f"Unknown llm: {llm}")

    from adapters.issue_tracker.zoho_sprints import ZohoSprintsAdapter
    adapters["issue_tracker"] = ZohoSprintsAdapter()

    from adapters.version_control.github import GitHubAdapter
    adapters["version_control"] = GitHubAdapter()

    from adapters.notification.teams import TeamsAdapter
    adapters["notification"] = TeamsAdapter()

    from adapters.cloud.aws import AWSAdapter
    adapters["cloud"] = AWSAdapter()

    from adapters.vector_store.chromadb import ChromaDBAdapter
    adapters["vector_store"] = ChromaDBAdapter()

    adapters["settings"] = {
        "default_repos": s.get("default_repos", []),
        "default_branch": s.get("default_branch", "main"),
    }

    return adapters
