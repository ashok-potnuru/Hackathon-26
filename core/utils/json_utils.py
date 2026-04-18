import json


def extract_json(text: str) -> dict:
    """Extract and parse the first JSON object from an LLM response string."""
    start = text.index("{")
    end = text.rindex("}") + 1
    return json.loads(text[start:end])
