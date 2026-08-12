"""
banking_server.py  —  PATTERN 8: Domain-specific MCP server (banking / FS)

DEMONSTRATES : A realistic vertical MCP server combining ALL primitives for a
               single business domain, backed by a seeded SQLite database.
PRIMITIVES   : tools (3: account_lookup, transaction_history, fraud_risk_score)
               resources (1: policy://basel-iii)
               prompts (1: regulatory_check)
STRENGTHS    : Encapsulates domain logic + data + compliance in one shareable
               server any agent in the org can reuse.
WEAKNESSES   : Tightly coupled to the bank's schema; needs careful access control.
"""
import sys, os, sqlite3, json, hashlib
sys.path.insert(0, os.path.dirname(__file__))
from _mcp_base import MCPServer

DB = os.path.join(os.path.dirname(__file__), "..", "banking.db")
srv = MCPServer("banking-server")

def _q(sql, args=()):
    conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
    conn.close(); return rows

@srv.tool("account_lookup",
          "Look up a bank customer account by customer_id (e.g. C-1001).",
          {"type": "object", "properties": {"customer_id": {"type": "string"}},
           "required": ["customer_id"]})
def account_lookup(customer_id):
    rows = _q("SELECT * FROM accounts WHERE customer_id=?", (customer_id,))
    return rows[0] if rows else {"error": f"No account: {customer_id}"}

@srv.tool("transaction_history",
          "Get recent transactions for a customer_id (most recent first).",
          {"type": "object", "properties": {
              "customer_id": {"type": "string"},
              "limit": {"type": "integer"}},
           "required": ["customer_id"]})
def transaction_history(customer_id, limit=5):
    limit = max(1, min(int(limit), 20))
    rows = _q("SELECT txn_date,type,amount,description FROM transactions "
              "WHERE customer_id=? ORDER BY txn_date DESC LIMIT ?",
              (customer_id, limit))
    return {"customer_id": customer_id, "count": len(rows), "transactions": rows}

@srv.tool("fraud_risk_score",
          "Compute a (mock) fraud risk score 0-100 for a customer_id.",
          {"type": "object", "properties": {"customer_id": {"type": "string"}},
           "required": ["customer_id"]})
def fraud_risk_score(customer_id):
    acct = _q("SELECT * FROM accounts WHERE customer_id=?", (customer_id,))
    if not acct:
        return {"error": f"No account: {customer_id}"}
    h = int(hashlib.md5(customer_id.encode()).hexdigest(), 16)
    score = h % 100
    band = "high" if score >= 70 else "medium" if score >= 40 else "low"
    return {"customer_id": customer_id, "fraud_risk_score": score,
            "risk_band": band, "note": "MOCK heuristic for demo"}

@srv.resource("policy://basel-iii", "Basel III / KYC Summary",
              "Capital adequacy & KYC compliance summary.")
def basel_doc():
    return ("BASEL III + KYC COMPLIANCE SUMMARY\n"
            "- Minimum Common Equity Tier 1 (CET1) ratio: 4.5%.\n"
            "- Capital conservation buffer: +2.5%.\n"
            "- Liquidity Coverage Ratio (LCR) >= 100%.\n"
            "- KYC: verify identity, screen sanctions, EDD for high-risk.\n"
            "- Report suspicious transactions to the FIU promptly.")

@srv.prompt("regulatory_check",
            "Template to assess whether an action is compliant.",
            [{"name": "action", "description": "The proposed action", "required": True},
             {"name": "customer_tier", "description": "Customer risk tier", "required": False}])
def regulatory_check(action, customer_tier="standard"):
    return (f"You are a banking compliance officer.\n"
            f"Customer tier: {customer_tier}\n"
            f"Proposed action: {action}\n\n"
            "Check this against KYC, AML, and Basel III rules. "
            "State CLEARLY: APPROVED or BLOCKED, with the specific rule cited.")

if __name__ == "__main__":
    srv.run()
