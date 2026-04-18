"""
Test ExplorerAgent in isolation.

What it does:
  - Takes an issue + some code files
  - Reads the code and decides which files MUST change vs. which are just context
  - Returns relevant line ranges per file

Run:
    source venv/bin/activate
    set -a && source .env && set +a
    python3 scripts/test_explorer.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts._llm_loader import load_llm
from core.agents.explorer_agent import ExplorerAgent

# ── Change these to test different issues ────────────────────────────────────
ISSUE_TITLE       = "Payment charge fails with 500 error"
ISSUE_DESCRIPTION = (
    "TypeError: Cannot read property 'amount' of undefined "
    "inside the charge handler when user checks out."
)

# Simulate code files that came back from the graph search
CODE_SECTIONS = {
    "services/payments/charge.handler.js": """\
const stripe = require('stripe')(process.env.STRIPE_KEY);

async function chargeCustomer(req, res) {
    const amount = req.body.payment.amount;   // <-- crashes if payment is undefined
    const currency = req.body.payment.currency;
    const customerId = req.body.customerId;

    const charge = await stripe.charges.create({ amount, currency, customer: customerId });
    res.json({ success: true, chargeId: charge.id });
}

module.exports = { chargeCustomer };
""",
    "models/order.js": """\
const mongoose = require('mongoose');

const orderSchema = new mongoose.Schema({
    customerId: String,
    items: Array,
    total: Number,
    status: { type: String, default: 'pending' },
});

module.exports = mongoose.model('Order', orderSchema);
""",
}
# ─────────────────────────────────────────────────────────────────────────────

llm   = load_llm()
agent = ExplorerAgent(llm)

print(f"\nRunning ExplorerAgent with model: {llm._model}")
print(f"Issue : {ISSUE_TITLE}\n")

result = agent.explore(ISSUE_TITLE, ISSUE_DESCRIPTION, CODE_SECTIONS)

print(f"Summary: {result.summary}\n")

print("Files that MUST change:")
for path, lines in result.must_change_files.items():
    print(f"  - {path}")

print("\nContext-only files (no changes needed):")
for path, lines in result.context_files.items():
    print(f"  - {path}")
