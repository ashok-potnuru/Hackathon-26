"""
Abstract base class that all LLM adapters must implement.
Methods to implement: analyze(prompt), generate_fix(context), review_fix(fix),
embed(text), health_check().
To add a new LLM provider: subclass this class and implement all methods.
"""
