"""
Orchestrates all 8 pipeline stages in sequence: Intake → Triage → Research →
Fix Generation → PR Creation → Developer Review → CI → Closure.
Inject adapters via the registry and pass models between stages.
Never call adapter APIs directly here — all adapter access must go through injected interfaces.
"""
