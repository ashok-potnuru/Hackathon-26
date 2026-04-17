"""
Stage 3: Searches git history, queries fix memory (ChromaDB), runs RAG codebase search,
and performs impact analysis to build context for fix generation.
Enforces a PR size guard — raises PRTooLargeError if more than MAX_FILES_FOR_AUTO_FIX files are affected.
Returns a ResearchContext that is passed directly to fix_generator.
"""
