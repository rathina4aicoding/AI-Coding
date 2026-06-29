"""
agent.py  —  ReAct agentic loop + all tool executors

TOOL CATEGORIES (for learners)
================================
Custom tools   YOUR code executes them. Claude emits tool_use; you run
               the function and return tool_result.
Server tools   Anthropic's infra executes them (web_search, web_fetch).
               You include them in the tools list; results appear in response.
MCP connector  Remote MCP server. Use client.beta.messages.create() +
               mcp_servers param (beta header required).
"""

import os, json, math, datetime, subprocess, sys, threading, time
from pathlib import Path
import requests
import anthropic
from db_tools import run_db_query, seed_db

api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY", "")
client = anthropic.Anthropic(api_key=api_key)
seed_db()

# ─────────────────────────────────────────────────────────────
# 1. EXTERNAL API TOOLS  (real public APIs, no key required)
# ─────────────────────────────────────────────────────────────

def get_weather(city: str) -> str:
    """Real-time weather via Open-Meteo (free, no API key)."""
    try:
        geo = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                           params={"name": city, "count": 1}, timeout=8).json()
        if not geo.get("results"):
            return json.dumps({"error": f"City not found: {city}"})
        r = geo["results"][0]
        wx = requests.get("https://api.open-meteo.com/v1/forecast",
                          params={"latitude": r["latitude"], "longitude": r["longitude"],
                                  "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
                                  "timezone": "auto"}, timeout=8).json()
        c = wx["current"]
        return json.dumps({"city": r["name"], "temperature_c": c["temperature_2m"],
                           "humidity_pct": c["relative_humidity_2m"],
                           "wind_kmh": c["wind_speed_10m"],
                           "weather_code": c["weather_code"], "source": "Open-Meteo"})
    except Exception as e:
        return json.dumps({"error": str(e)})

def get_fx_rate(base: str, target: str) -> str:
    """Live FX rate via Frankfurter / ECB (free, no key)."""
    try:
        r = requests.get("https://api.frankfurter.app/latest",
                         params={"from": base.upper(), "to": target.upper()}, timeout=8).json()
        return json.dumps({"base": base.upper(), "target": target.upper(),
                           "rate": r["rates"].get(target.upper()), "date": r.get("date"),
                           "source": "Frankfurter/ECB"})
    except Exception as e:
        return json.dumps({"error": str(e)})

# ─────────────────────────────────────────────────────────────
# 2. LOCAL PYTHON FUNCTION TOOLS  (pure, no network)
# ─────────────────────────────────────────────────────────────

def calculate(expression: str) -> str:
    """Safely evaluate a math expression without arbitrary eval."""
    safe = {"sqrt": math.sqrt, "log": math.log, "log10": math.log10,
            "sin": math.sin, "cos": math.cos, "tan": math.tan,
            "pi": math.pi, "e": math.e, "abs": abs, "round": round, "pow": pow}
    try:
        result = eval(expression, {"__builtins__": {}}, safe)  # noqa: S307
        return json.dumps({"expression": expression, "result": result})
    except Exception as exc:
        return json.dumps({"error": f"Cannot evaluate '{expression}': {exc}"})

def date_info(query: str = "today") -> str:
    """Return current date, day, week number, days to year-end."""
    now = datetime.datetime.now()
    return json.dumps({
        "today": now.strftime("%Y-%m-%d"),
        "time_utc": datetime.datetime.utcnow().strftime("%H:%M:%S"),
        "day_of_week": now.strftime("%A"),
        "week_number": now.isocalendar()[1],
        "days_until_year_end": (datetime.datetime(now.year, 12, 31) - now).days,
    })

# ─────────────────────────────────────────────────────────────
# 4. LOCAL MCP SERVER  (stdio subprocess)
# ─────────────────────────────────────────────────────────────
_mcp_proc = None
_mcp_lock = threading.Lock()
_mcp_id   = 0

def _ensure_mcp():
    global _mcp_proc, _mcp_id
    with _mcp_lock:
        if _mcp_proc is None or _mcp_proc.poll() is not None:
            srv = Path(__file__).parent / "local_mcp_server.py"
            _mcp_proc = subprocess.Popen(
                [sys.executable, str(srv)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
            _mcp_id += 1
            _mcp_proc.stdin.write(json.dumps({
                "jsonrpc":"2.0","id":_mcp_id,"method":"initialize",
                "params":{"protocolVersion":"2024-11-05","capabilities":{},
                          "clientInfo":{"name":"demo","version":"1.0"}}}) + "\n")
            _mcp_proc.stdin.flush()
            _mcp_proc.stdout.readline()  # consume initialize response

def call_local_mcp(tool_name: str, arguments: dict) -> str:
    """Send a tool call to the local stdio MCP server subprocess."""
    try:
        global _mcp_id
        _ensure_mcp()
        _mcp_id += 1
        req = {"jsonrpc":"2.0","id":_mcp_id,"method":"tools/call",
               "params":{"name": tool_name, "arguments": arguments}}
        _mcp_proc.stdin.write(json.dumps(req) + "\n")
        _mcp_proc.stdin.flush()
        resp = json.loads(_mcp_proc.stdout.readline().strip())
        if "error" in resp:
            return json.dumps({"error": resp["error"]["message"]})
        return "\n".join(c.get("text","") for c in resp.get("result",{}).get("content",[]))
    except Exception as e:
        return json.dumps({"error": f"Local MCP error: {e}"})

# ─────────────────────────────────────────────────────────────
# 5. REMOTE MCP CONNECTOR  (Anthropic beta — server-side MCP)
# Uses client.beta.messages.create() with mcp_servers param.
# Falls back gracefully if the remote server is unavailable.
# ─────────────────────────────────────────────────────────────
REMOTE_MCP_URL  = os.environ.get("REMOTE_MCP_URL", "")   # set in .env
REMOTE_MCP_TOKEN = os.environ.get("REMOTE_MCP_TOKEN", "")

def run_agent_with_remote_mcp(user_message: str, model: str) -> dict:
    """
    Demonstrate the Anthropic MCP connector beta.
    Claude handles connection + tool discovery + execution server-side.
    Only called if REMOTE_MCP_URL is set in .env.
    """
    if not REMOTE_MCP_URL:
        return {"answer": "REMOTE_MCP_URL not configured — skipping remote MCP demo.",
                "tool_calls": [], "usage": {}, "cost_usd": 0}
    mcp_server = {"type": "url", "url": REMOTE_MCP_URL, "name": "remote-mcp"}
    if REMOTE_MCP_TOKEN:
        mcp_server["authorization_token"] = REMOTE_MCP_TOKEN
    try:
        resp = client.beta.messages.create(
            model=model, max_tokens=1024,
            messages=[{"role": "user", "content": user_message}],
            mcp_servers=[mcp_server],
            tools=[{"type": "mcp_toolset", "mcp_server_name": "remote-mcp"}],
            betas=["mcp-client-2025-11-20"],
        )
        answer = "\n".join(b.text for b in resp.content if hasattr(b,"text"))
        return {"answer": answer, "tool_calls": [], "usage": {}, "cost_usd": 0}
    except Exception as e:
        return {"answer": f"Remote MCP error: {e}", "tool_calls": [], "usage": {}, "cost_usd": 0}

# ─────────────────────────────────────────────────────────────
# TOOL SCHEMA REGISTRY  (what Claude sees as tool definitions)
# ─────────────────────────────────────────────────────────────

CUSTOM_TOOL_SCHEMAS = [
    # -- External API tools --
    {"name": "get_weather",
     "description": "Get real-time weather for any city (Open-Meteo, no key needed). "
                    "Returns temperature °C, humidity %, wind km/h.",
     "input_schema": {"type":"object",
                      "properties":{"city":{"type":"string","description":"City name e.g. Chennai, London"}},
                      "required":["city"]}},
    {"name": "get_fx_rate",
     "description": "Get live currency exchange rate via Frankfurter/ECB. "
                    "Use ISO codes: USD, EUR, INR, GBP, JPY.",
     "input_schema": {"type":"object",
                      "properties":{"base":{"type":"string","description":"Base currency e.g. USD"},
                                    "target":{"type":"string","description":"Target currency e.g. INR"}},
                      "required":["base","target"]}},
    # -- Local function tools --
    {"name": "calculate",
     "description": "Safely evaluate a math expression. "
                    "Supports: +,-,*,/,**,sqrt,log,sin,cos,pi,e. "
                    "Example: 'sqrt(2)*pi' or '(100*1.08**5)'.",
     "input_schema": {"type":"object",
                      "properties":{"expression":{"type":"string","description":"Math expression"}},
                      "required":["expression"]}},
    {"name": "date_info",
     "description": "Return today's date, day of week, week number, days until year-end.",
     "input_schema": {"type":"object",
                      "properties":{"query":{"type":"string","description":"Optional query context"}},
                      "required":[]}},
    # -- Database tool --
    {"name": "query_database",
     "description": "Query the local SQLite banking demo database. "
                    "Tables: customers, orders, transactions. "
                    "Use filters dict e.g. {\"segment\":\"premium\"}.",
     "input_schema": {"type":"object",
                      "properties":{"table":{"type":"string",
                                             "enum":["customers","orders","transactions"]},
                                    "filters":{"type":"object",
                                               "description":"Column=value equality filters"},
                                    "limit":{"type":"integer",
                                             "description":"Max rows (1-50, default 10)"}},
                      "required":["table"]}},
    # -- Local MCP tools --
    {"name": "mcp_unit_converter",
     "description": "[Local MCP server] Convert between units: km/miles, kg/lbs, C/F, m/ft.",
     "input_schema": {"type":"object",
                      "properties":{"value":{"type":"number","description":"Numeric value"},
                                    "from_unit":{"type":"string","description":"e.g. km, kg, C"},
                                    "to_unit":{"type":"string","description":"e.g. miles, lbs, F"}},
                      "required":["value","from_unit","to_unit"]}},
    {"name": "mcp_stock_quote",
     "description": "[Local MCP server] Stock price quote for a ticker. "
                    "Returns mock/demo data — swap for real API in production.",
     "input_schema": {"type":"object",
                      "properties":{"ticker":{"type":"string","description":"e.g. AAPL, INFY, TCS"}},
                      "required":["ticker"]}},
]

# Server-side tools — Anthropic's infra executes these; your code just names them
SERVER_TOOL_SCHEMAS = [
    {"type": "web_search_20260209", "name": "web_search"},   # live web search
    {"type": "web_fetch_20260209",  "name": "web_fetch"},    # fetch full page content
    # {"type": "code_execution_20260120", "name": "code_execution"},  # Python sandbox
]

ALL_TOOL_NAMES = [t["name"] for t in CUSTOM_TOOL_SCHEMAS] + ["web_search", "web_fetch"]

# ─────────────────────────────────────────────────────────────
# DISPATCHER  — route tool name → executor
# ─────────────────────────────────────────────────────────────

def dispatch_tool(name: str, args: dict) -> str:
    """Execute a custom (client-side) tool and return result string."""
    if name == "get_weather":        return get_weather(**args)
    if name == "get_fx_rate":        return get_fx_rate(**args)
    if name == "calculate":          return calculate(**args)
    if name == "date_info":          return date_info(**args)
    if name == "query_database":     return run_db_query(
                                         args["table"], args.get("filters"), args.get("limit",10))
    if name == "mcp_unit_converter": return call_local_mcp("unit_converter", args)
    if name == "mcp_stock_quote":    return call_local_mcp("stock_quote_mock", args)
    return json.dumps({"error": f"Unknown tool: {name}"})

# ─────────────────────────────────────────────────────────────
# REACT AGENTIC LOOP
# ─────────────────────────────────────────────────────────────

def run_agent(user_message: str, model: str, enabled_tools: list,
              use_server_tools: bool = True, history: list = None) -> dict:
    """
    ReAct agentic loop:
      1. Send messages + tool schemas to Claude.
      2. If stop_reason='tool_use': dispatch each tool_use block,
         append tool_result, repeat.
      3. If stop_reason='end_turn': return final text answer.
    Supports parallel tool calls in a single turn.
    """
    messages = list(history or []) + [{"role":"user","content":user_message}]
    active_custom = [t for t in CUSTOM_TOOL_SCHEMAS if t["name"] in enabled_tools]
    active_server = SERVER_TOOL_SCHEMAS if use_server_tools else []
    all_tools     = active_custom + active_server

    tool_calls_log = []
    total_usage    = {"input_tokens":0, "output_tokens":0}
    final_answer   = ""

    for _ in range(12):   # iteration cap (guardrail against infinite loops)
        resp = client.messages.create(
            model=model, max_tokens=2048,
            system=("You are a helpful AI assistant for banking and financial services. "
                    "Use tools when they provide better or real-time information. "
                    "Think step by step, pick the right tool, and explain your reasoning."),
            tools=all_tools if all_tools else [],
            messages=messages,
        )
        total_usage["input_tokens"]  += resp.usage.input_tokens
        total_usage["output_tokens"] += resp.usage.output_tokens

        text_parts = [b.text for b in resp.content if b.type == "text"]
        if text_parts:
            final_answer = "\n".join(text_parts)

        if resp.stop_reason == "end_turn":
            break

        if resp.stop_reason == "tool_use":
            tool_blocks = [b for b in resp.content if b.type == "tool_use"]
            if not tool_blocks:
                break
            messages.append({"role":"assistant","content": resp.content})
            tool_results = []
            for blk in tool_blocks:
                t0 = time.time()
                try:
                    result = dispatch_tool(blk.name, blk.input)
                except Exception as exc:
                    result = json.dumps({"error": str(exc)})
                elapsed = round(time.time()-t0, 3)
                tool_calls_log.append({"tool":blk.name,"args":blk.input,
                                       "result":result,"elapsed_s":elapsed})
                tool_results.append({"type":"tool_result","tool_use_id":blk.id,
                                     "content":result})
            messages.append({"role":"user","content":tool_results})
            continue
        break  # max_tokens or other stop reason

    # Rough cost estimate (Sonnet 4.6 rates)
    cost = (total_usage["input_tokens"]/1e6*3.0 +
            total_usage["output_tokens"]/1e6*15.0)
    return {"answer": final_answer, "tool_calls": tool_calls_log,
            "usage": total_usage, "cost_usd": round(cost,6)}
