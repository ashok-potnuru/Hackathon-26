"""Shared helper — loads the LLM adapter from settings.yaml without touching other adapters."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml


def load_llm():
    with open("settings.yaml") as f:
        s = yaml.safe_load(f)
    provider = s.get("llm", "claude")
    model    = s.get("model")
    if provider == "openai":
        from adapters.llm.openai import OpenAIAdapter
        return OpenAIAdapter(model=model)
    elif provider == "gemini":
        from adapters.llm.gemini import GeminiAdapter
        return GeminiAdapter()
    else:
        from adapters.llm.claude import ClaudeAdapter
        return ClaudeAdapter(model=model)
