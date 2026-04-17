"""
Abstract base class that all vector store adapters must implement.
Methods to implement: store_fix(issue_id, issue_text, fix_text),
search_similar(issue_text, top_k), health_check().
Used by the research stage for fix memory lookup — never call a concrete store from core/.
"""
