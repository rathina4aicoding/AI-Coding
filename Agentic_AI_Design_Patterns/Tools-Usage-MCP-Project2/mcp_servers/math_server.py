"""
math_server.py  —  PATTERN 3 helper: second MCP server for fan-out orchestration

DEMONSTRATES : A SEPARATE specialised server (maths/calculation only) so the
               agent must ROUTE the right subtask to the right server.
PRIMITIVES   : tools (2)
Paired with general_server.py to show multi-server orchestration.
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(__file__))
from _mcp_base import MCPServer

srv = MCPServer("math-server")

@srv.tool("calculate",
          "Safely evaluate a maths expression (sqrt, log, sin, cos, pi, e).",
          {"type": "object", "properties": {"expression": {"type": "string"}},
           "required": ["expression"]})
def calculate(expression):
    safe = {"sqrt": math.sqrt, "log": math.log, "sin": math.sin,
            "cos": math.cos, "tan": math.tan, "pi": math.pi, "e": math.e,
            "abs": abs, "round": round, "pow": pow}
    try:
        return {"expression": expression,
                "result": eval(expression, {"__builtins__": {}}, safe)}
    except Exception as e:
        return {"error": str(e)}

@srv.tool("compound_interest",
          "Compute compound interest. principal, annual_rate (%), years.",
          {"type": "object", "properties": {
              "principal": {"type": "number"}, "annual_rate": {"type": "number"},
              "years": {"type": "number"}},
           "required": ["principal", "annual_rate", "years"]})
def compound_interest(principal, annual_rate, years):
    final = principal * (1 + annual_rate/100) ** years
    return {"principal": principal, "annual_rate": annual_rate, "years": years,
            "final_amount": round(final, 2),
            "interest_earned": round(final - principal, 2)}

if __name__ == "__main__":
    srv.run()
