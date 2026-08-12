"""
stateful_server.py  —  PATTERN 7: Stateful vs Stateless architecture contrast

DEMONSTRATES : Two modes in one server, switched by the MCP_MODE env var:
   - MCP_MODE=stateless : every call is independent. No memory between calls.
                          Scales behind a round-robin load balancer with NO
                          sticky sessions. This is the MCP 2026 spec direction.
   - MCP_MODE=stateful  : keeps an in-memory session store. set_current_customer
                          in one call is remembered by who_is_current in the next.

WHY STATELESS WINS IN PRODUCTION:
   A stateless server can run as N identical replicas; any replica can serve
   any request, so you get horizontal scale, easy restarts, and no session
   affinity at the load balancer. Stateful servers need sticky sessions or a
   shared store, which is harder to scale and more fragile.
PRIMITIVES : tools (2)
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from _mcp_base import MCPServer

MODE = os.environ.get("MCP_MODE", "stateless")
srv = MCPServer(f"{MODE}-server")
_session = {}   # only used in stateful mode

@srv.tool("set_current_customer",
          "Set the 'current customer' for this session.",
          {"type": "object", "properties": {"customer_id": {"type": "string"}},
           "required": ["customer_id"]})
def set_current_customer(customer_id):
    if MODE == "stateful":
        _session["current_customer"] = customer_id
        return {"mode": MODE, "set": customer_id,
                "note": "Remembered for next call (stateful)."}
    return {"mode": MODE, "set": customer_id,
            "note": "NOT remembered — stateless servers keep no session memory. "
                    "Pass customer_id explicitly on every call."}

@srv.tool("who_is_current",
          "Return the 'current customer' set earlier this session.",
          {"type": "object", "properties": {}, "required": []})
def who_is_current():
    if MODE == "stateful":
        cur = _session.get("current_customer")
        return {"mode": MODE, "current_customer": cur or "(none set)"}
    return {"mode": MODE, "current_customer": "(stateless: nothing remembered)",
            "note": "Each request is independent — by design."}

if __name__ == "__main__":
    srv.run()
