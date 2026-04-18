"""
Test ReviewerAgent in isolation.

What it does:
  - Takes the original broken code + the proposed fix
  - Runs 7 adversarial checks (correctness, security, regression, edge cases, etc.)
  - Returns PASS / FAIL / PARTIAL + specific feedback

Run:
    source venv/bin/activate
    set -a && source .env && set +a
    python3 scripts/test_reviewer.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts._llm_loader import load_llm
from core.agents.reviewer_agent import ReviewerAgent

# ── Change these to test different fixes ─────────────────────────────────────
ISSUE_DESCRIPTION = (
    "TypeError: Cannot read property 'amount' of undefined "
    "inside the charge handler when user checks out."
)

ORIGINAL_CODE = {
    "services/payments/charge.handler.js": """\
async function chargeCustomer(req, res) {
    const amount = req.body.payment.amount;   // crashes if payment is undefined
    const currency = req.body.payment.currency;
    const charge = await stripe.charges.create({ amount, currency });
    res.json({ success: true, chargeId: charge.id });
}
""",
}

PROPOSED_FIX = {
    "services/payments/charge.handler.js": """\
async function chargeCustomer(req, res) {
    if (!req.body.payment || !req.body.payment.amount) {
        return res.status(400).json({ error: 'Missing payment details' });
    }
    const { amount, currency } = req.body.payment;
    try {
        const charge = await stripe.charges.create({ amount, currency });
        res.json({ success: true, chargeId: charge.id });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
}
""",
}
# ─────────────────────────────────────────────────────────────────────────────

llm   = load_llm()
agent = ReviewerAgent(llm)

print(f"\nRunning ReviewerAgent with model: {llm._model}\n")

result = agent.review(
    description=ISSUE_DESCRIPTION,
    original_code=ORIGINAL_CODE,
    proposed_changes=PROPOSED_FIX,
)

print(f"Verdict     : {result.verdict}")
print(f"Approved    : {result.approved}")
print(f"Security OK : {result.security_ok}")

if result.checks:
    print("\nPer-check results:")
    for check, outcome in result.checks.items():
        print(f"  {check:<20} {outcome}")

if result.feedback:
    print(f"\nFeedback: {result.feedback}")

if result.issues:
    print("\nIssues found:")
    for issue in result.issues:
        print(f"  - {issue}")
