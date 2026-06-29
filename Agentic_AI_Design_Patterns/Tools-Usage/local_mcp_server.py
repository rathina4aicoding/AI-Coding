"""
local_mcp_server.py
--------------------
A minimal local MCP server that Claude can call via the stdio transport.
It exposes two tools: unit_converter and stock_quote_mock.
Run standalone:  python local_mcp_server.py
Claude Code / mcp SDK spawns it automatically as a subprocess.
"""

import sys
import json
import math

# --------------------------------------------------------------------------
# MCP wire protocol helpers (JSON-RPC 2.0 over stdin/stdout)
# --------------------------------------------------------------------------

def send(obj: dict):
    line = json.dumps(obj)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()

def recv() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line.strip())

# --------------------------------------------------------------------------
# Tool implementations
# --------------------------------------------------------------------------

def unit_converter(value: float, from_unit: str, to_unit: str) -> str:
    """Convert between common units."""
    conversions = {
        ("km",  "miles"): lambda v: v * 0.621371,
        ("miles","km"):   lambda v: v * 1.60934,
        ("kg",  "lbs"):   lambda v: v * 2.20462,
        ("lbs", "kg"):    lambda v: v * 0.453592,
        ("c",   "f"):     lambda v: v * 9/5 + 32,
        ("f",   "c"):     lambda v: (v - 32) * 5/9,
        ("m",   "ft"):    lambda v: v * 3.28084,
        ("ft",  "m"):     lambda v: v * 0.3048,
    }
    key = (from_unit.lower().strip(), to_unit.lower().strip())
    if key not in conversions:
        return f"Unsupported conversion: {from_unit} → {to_unit}. Supported: {list(conversions.keys())}"
    result = conversions[key](value)
    return f"{value} {from_unit} = {result:.4f} {to_unit}"


def stock_quote_mock(ticker: str) -> dict:
    """
    Returns a mock stock quote.
    (Real production: swap for yfinance or a financial API key.)
    """
    import hashlib, datetime
    # deterministic fake price based on ticker hash so it looks consistent
    h = int(hashlib.md5(ticker.upper().encode()).hexdigest(), 16)
    price = round(50 + (h % 95000) / 1000, 2)
    change = round((h % 1000) / 100 - 5, 2)
    return {
        "ticker": ticker.upper(),
        "price": price,
        "change": change,
        "change_pct": round(change / price * 100, 2),
        "as_of": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "note": "MOCK DATA — replace with real API for production",
    }


# --------------------------------------------------------------------------
# MCP server loop
# --------------------------------------------------------------------------

TOOLS = [
    {
        "name": "unit_converter",
        "description": "Convert a numeric value between units of measurement. "
                       "Supported: km/miles, kg/lbs, C/F, m/ft.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "value":     {"type": "number",  "description": "The numeric value to convert"},
                "from_unit": {"type": "string",  "description": "Source unit (e.g. km, kg, C)"},
                "to_unit":   {"type": "string",  "description": "Target unit (e.g. miles, lbs, F)"},
            },
            "required": ["value", "from_unit", "to_unit"],
        },
    },
    {
        "name": "stock_quote_mock",
        "description": "Return a stock price quote for a given ticker symbol. "
                       "Returns mock/demo data; replace with a real API in production.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol e.g. AAPL"},
            },
            "required": ["ticker"],
        },
    },
]


def main():
    """
    Speaks the MCP stdio protocol (JSON-RPC 2.0).
    Handles: initialize, tools/list, tools/call.
    """
    while True:
        msg = recv()
        if msg is None:
            break

        method  = msg.get("method", "")
        req_id  = msg.get("id")
        params  = msg.get("params", {})

        # ---- initialize handshake ----
        if method == "initialize":
            send({
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "local-demo-mcp", "version": "1.0.0"},
                }
            })

        # ---- list tools ----
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}})

        # ---- call a tool ----
        elif method == "tools/call":
            tool_name = params.get("name")
            args      = params.get("arguments", {})
            try:
                if tool_name == "unit_converter":
                    result = unit_converter(**args)
                    content = [{"type": "text", "text": result}]
                elif tool_name == "stock_quote_mock":
                    result = stock_quote_mock(**args)
                    content = [{"type": "text", "text": json.dumps(result, indent=2)}]
                else:
                    content = [{"type": "text", "text": f"Unknown tool: {tool_name}"}]
                send({"jsonrpc": "2.0", "id": req_id, "result": {"content": content}})
            except Exception as exc:
                send({
                    "jsonrpc": "2.0", "id": req_id,
                    "error": {"code": -32603, "message": str(exc)},
                })

        # ---- notifications (no response needed) ----
        elif method.startswith("notifications/"):
            pass

        # ---- unknown ----
        else:
            send({
                "jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            })


if __name__ == "__main__":
    main()
