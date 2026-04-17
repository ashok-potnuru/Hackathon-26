"""
Stage 8: Runs after a PR is merged — updates Zoho status to Fixed, stores the fix in
ChromaDB memory for future RAG lookups, and sends a Teams closure message with a feedback prompt.
Thumbs up/down feedback is persisted to ChromaDB to improve fix quality over time.
Never call adapter APIs directly — use injected adapter interfaces.
"""
