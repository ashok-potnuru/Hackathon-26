import json
import re


def extract_json(text: str) -> dict:
    """Extract and parse the first JSON object from an LLM response string.

    Handles common LLM JSON issues:
    - Markdown code fences (```json ... ```)
    - Unescaped control characters (newlines inside string values)
    """
    # Strip markdown fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text.strip(), flags=re.MULTILINE)
    text = text.strip()

    start = text.index("{")
    end = text.rindex("}") + 1
    raw = text[start:end]

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fix unescaped literal newlines inside JSON strings (most common LLM mistake).
        # Replace \n that appear inside quoted strings with \\n.
        cleaned = _fix_unescaped_newlines(raw)
        return json.loads(cleaned)


def _fix_unescaped_newlines(s: str) -> str:
    """Replace literal newlines inside JSON string values with \\n escape sequences.

    This is a targeted fix: we only modify characters that appear between
    JSON string delimiters, leaving structural characters alone.
    """
    result = []
    in_string = False
    escape_next = False
    for ch in s:
        if escape_next:
            result.append(ch)
            escape_next = False
            continue
        if ch == "\\":
            result.append(ch)
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string and ch == "\n":
            result.append("\\n")
            continue
        if in_string and ch == "\r":
            result.append("\\r")
            continue
        if in_string and ch == "\t":
            result.append("\\t")
            continue
        result.append(ch)
    return "".join(result)
