"""
general_server.py  —  PATTERN 1: Local stdio MCP server (custom, bundled)

DEMONSTRATES : A complete custom MCP server with ALL THREE primitives.
PRIMITIVES   : tools (3), resources (2), prompts (1)
STRENGTHS    : Full control, zero network, easy to debug, runs anywhere.
WEAKNESSES   : Single process; you maintain it; not shareable across orgs
               like a published server.

This same server is reused by Pattern 4 (resources) and Pattern 5 (prompts).

MCP WIRE PROTOCOL (this server):
  initialize -> serverInfo
  tools/list -> [unit_converter, stock_quote, date_calculator]
  resources/list -> [policy://kyc-summary, customer://C-1001]
  prompts/list -> [structured_analysis]
"""
import sys, os, hashlib, datetime, json
sys.path.insert(0, os.path.dirname(__file__))
from _mcp_base import MCPServer

srv = MCPServer("general-demo-server")

# ---------------- TOOLS (imperative actions) ----------------
@srv.tool("unit_converter",
          "Convert a value between units: km/miles, kg/lbs, C/F, m/ft.",
          {"type": "object", "properties": {
              "value": {"type": "number"}, "from_unit": {"type": "string"},
              "to_unit": {"type": "string"}},
           "required": ["value", "from_unit", "to_unit"]})
def unit_converter(value, from_unit, to_unit):
    table = {("km","miles"): lambda v: v*0.621371,
             ("miles","km"): lambda v: v*1.60934,
             ("kg","lbs"):   lambda v: v*2.20462,
             ("lbs","kg"):   lambda v: v*0.453592,
             ("c","f"):      lambda v: v*9/5+32,
             ("f","c"):      lambda v: (v-32)*5/9,
             ("m","ft"):     lambda v: v*3.28084,
             ("ft","m"):     lambda v: v*0.3048}
    key = (from_unit.lower(), to_unit.lower())
    if key not in table:
        return {"error": f"Unsupported: {from_unit}->{to_unit}"}
    return {"value": value, "from": from_unit, "to": to_unit,
            "result": round(table[key](value), 4)}

@srv.tool("stock_quote",
          "Get a (mock) stock price quote for a ticker symbol.",
          {"type": "object",
           "properties": {"ticker": {"type": "string"}},
           "required": ["ticker"]})
def stock_quote(ticker):
    h = int(hashlib.md5(ticker.upper().encode()).hexdigest(), 16)
    price = round(50 + (h % 95000)/1000, 2)
    return {"ticker": ticker.upper(), "price": price,
            "currency": "USD", "note": "MOCK DATA — demo only",
            "as_of": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}

@srv.tool("date_calculator",
          "Calculate days between today and a target date (YYYY-MM-DD).",
          {"type": "object",
           "properties": {"target_date": {"type": "string"}},
           "required": ["target_date"]})
def date_calculator(target_date):
    today = datetime.date.today()
    try:
        tgt = datetime.date.fromisoformat(target_date)
    except ValueError:
        return {"error": "Use YYYY-MM-DD format"}
    delta = (tgt - today).days
    return {"today": today.isoformat(), "target": target_date,
            "days_between": delta,
            "direction": "future" if delta > 0 else "past"}

# ---------------- RESOURCES (declarative data) ----------------
@srv.resource("policy://kyc-summary", "KYC Policy Summary",
              "Bank KYC onboarding policy (summary).")
def kyc_doc():
    return ("KYC POLICY SUMMARY\n"
            "1. Verify government photo ID for every new account.\n"
            "2. Capture proof of address dated within 3 months.\n"
            "3. Screen all applicants against sanctions watchlists.\n"
            "4. Apply Enhanced Due Diligence for high-risk customers.\n"
            "5. Refresh KYC records every 24 months.")

@srv.resource("customer://C-1001", "Customer Record C-1001",
              "Structured record for customer C-1001.", mime="application/json")
def customer_rec():
    return json.dumps({"id": "C-1001", "name": "Arjun Mehta",
                       "segment": "premium", "city": "Mumbai",
                       "kyc_status": "verified", "risk_tier": "low"})

# ---------------- PROMPTS (reusable templates) ----------------
@srv.prompt("structured_analysis",
            "A reusable template that asks for a structured analysis.",
            [{"name": "topic", "description": "What to analyse", "required": True},
             {"name": "audience", "description": "Who it is for", "required": False}])
def structured_analysis(topic, audience="a general audience"):
    return (f"Analyse the following topic for {audience}.\n"
            f"TOPIC: {topic}\n\n"
            "Structure your answer as:\n"
            "1. Summary (2 sentences)\n2. Key points (3 bullets)\n"
            "3. Risks or caveats\n4. Recommended next step")

if __name__ == "__main__":
    srv.run()
