"""
Test PlannerAgent in isolation.

What it does:
  - Takes an issue title + description
  - Uses LLM to extract keywords (e.g. "payment", "charge", "amount")
  - Searches the knowledge graph for matching files
  - Returns a list of files that need to change

Run:
    source venv/bin/activate
    set -a && source .env && set +a
    python3 scripts/test_planner.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts._llm_loader import load_llm
from core.agents.planner_agent import PlannerAgent
from core.utils.graph_navigator import get_navigator

# ── Change these to test different issues ────────────────────────────────────
ISSUE_TITLE       = "Payment charge fails with 500 error"
ISSUE_DESCRIPTION = (
    "When a user checks out, the /api/payments/charge endpoint returns HTTP 500. "
    "Error log shows: TypeError: Cannot read property 'amount' of undefined."
)
# ─────────────────────────────────────────────────────────────────────────────

llm   = load_llm()
nav   = get_navigator()
agent = PlannerAgent(llm, nav)

print(f"\nRunning PlannerAgent with model: {llm._model}")
print(f"Issue : {ISSUE_TITLE}\n")

result = agent.plan(ISSUE_TITLE, ISSUE_DESCRIPTION)

print(f"Keywords extracted : {result.keywords_extracted}")
print(f"Change type        : {result.change_type}")
print(f"Files to fix ({len(result.target_files)}):")
for f in result.target_files:
    print(f"  - {f}")
print(f"\nReasoning: {result.reasoning}")
