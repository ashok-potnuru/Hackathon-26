"""
Stage 4: Generates a code fix using the LLM, produces a regression test, runs a Claude
self-review pass, executes a security scan, and enforces linting before accepting the fix.
Retries up to MAX_FIX_RETRIES on any failure before giving up.
Returns a FixModel on success.
"""
