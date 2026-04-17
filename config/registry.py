"""
Reads settings.yaml (or a tenant-specific config override) and returns instantiated adapter objects.
This is the ONLY place in the codebase that imports concrete adapter classes.
Core modules and pipeline stages must never import adapters directly — they receive them via registry.
"""
