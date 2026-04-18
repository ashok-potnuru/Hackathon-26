"""
Test CoderAgent in isolation.

What it does:
  - Takes an issue + the files that need fixing
  - Generates complete fixed file contents
  - Returns confidence score + reasoning

Run:
    source venv/bin/activate
    set -a && source .env && set +a
    python3 scripts/test_coder.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts._llm_loader import load_llm
from core.agents.coder_agent import CoderAgent

# ── Change these to test different issues ────────────────────────────────────
ISSUE_TITLE       = "Payment charge fails with 500 error"
ISSUE_DESCRIPTION = (
    "TypeError: Cannot read property 'amount' of undefined "
    "inside the charge handler when user checks out."
)

# The broken code you want the agent to fix
CODE_TO_FIX = {
    "services/payments/charge.handler.js": """\
const stripe = require('stripe')(process.env.STRIPE_KEY);

async function chargeCustomer(req, res) {
    const amount = req.body.payment.amount;   // crashes if payment is undefined
    const currency = req.body.payment.currency;
    const customerId = req.body.customerId;

    const charge = await stripe.charges.create({ amount, currency, customer: customerId });
    res.json({ success: true, chargeId: charge.id });
}

module.exports = { chargeCustomer };
""",
}

# Optional: paste feedback from reviewer to test the retry loop
REVIEWER_FEEDBACK = ""   # e.g. "You forgot to validate the currency field"
# ─────────────────────────────────────────────────────────────────────────────

llm   = load_llm()
agent = CoderAgent(llm)

print(f"\nRunning CoderAgent with model: {llm._model}")
print(f"Issue : {ISSUE_TITLE}\n")

result = agent.generate(
    title=ISSUE_TITLE,
    description=ISSUE_DESCRIPTION,
    code_context=CODE_TO_FIX,
    reviewer_feedback=REVIEWER_FEEDBACK,
)

print(f"Confidence : {result.confidence:.2f}")
print(f"Reasoning  : {result.reasoning}\n")

print(f"Files generated ({len(result.file_contents)}):")
for path, content in result.file_contents.items():
    print(f"\n── {path} ──")
    print(content[:1000])
    if len(content) > 1000:
        print(f"... ({len(content)} chars total)")
