"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           MCP EXPLORER  —  Transports & Primitives                         ║
║  Teal Trust Teaching Tool  |  One file, 8 tabs, beginner-friendly           ║
╚══════════════════════════════════════════════════════════════════════════════╝

HOW TO RUN
----------
  pip install gradio anthropic mcp python-dotenv
  # Create a .env file with:  ANTHROPIC_API_KEY=sk-ant-...
  python app.py
  # Open http://localhost:7860 in your browser

WHAT YOU'LL SEE
---------------
  Tab 1-3 : Three MCP transports  (stdio / HTTP / WebSocket)
  Tab 4-8 : Five MCP primitives   (Tools / Resources / Prompts / Sampling / Roots)

Each tab shows:
  ① A plain-English explanation of the concept
  ② The RAW JSON-RPC 2.0 message that travels on the wire
  ③ A LIVE demo you can run (click a button, see the real result)
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import textwrap
import threading
from datetime import datetime, timedelta
from typing import Any

import gradio as gr
from dotenv import load_dotenv

# ── optional: real Anthropic client for Sampling demo ────────────────────────
load_dotenv()
_API_KEY = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY", "")
try:
    from anthropic import Anthropic
    _anthropic = Anthropic(api_key=_API_KEY) if _API_KEY else None
except Exception:
    _anthropic = None

# ── Colour palette (used in labels only, not in Gradio theme) ────────────────
TEAL, MINT, INK = "#028090", "#02C39A", "#0B2E33"

# ═══════════════════════════════════════════════════════════════════════════════
#  SHARED HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _pretty(obj: Any) -> str:
    """Return a pretty-printed JSON string of any serialisable object."""
    return json.dumps(obj, indent=2, default=str)


def _jsonrpc_request(method: str, params: dict, req_id: int = 1) -> dict:
    """Build a well-formed JSON-RPC 2.0 request dict."""
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}


def _jsonrpc_result(req_id: int, result: Any) -> dict:
    """Build a well-formed JSON-RPC 2.0 success response dict."""
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _jsonrpc_error(req_id: int, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


# ═══════════════════════════════════════════════════════════════════════════════
#  MINI IN-PROCESS MCP SERVER  (no external process needed for most demos)
# ═══════════════════════════════════════════════════════════════════════════════

class MiniMCPServer:
    """
    A tiny, self-contained MCP server that runs inside the same Python process.

    It deliberately mimics the real JSON-RPC message shapes so beginners see
    exactly what travels on the wire — without needing a subprocess or a network.
    """

    def __init__(self, name: str = "MiniServer"):
        self.name = name
        self._tools: dict[str, dict] = {}
        self._resources: dict[str, Any] = {}
        self._prompts: dict[str, dict] = {}
        self._roots: list[dict] = []          # filled by the client (Roots primitive)

    # ── Registration helpers ─────────────────────────────────────────────────

    def register_tool(self, name: str, description: str, schema: dict, fn):
        self._tools[name] = {"description": description, "inputSchema": schema, "fn": fn}

    def register_resource(self, uri: str, description: str, value: Any):
        self._resources[uri] = {"description": description, "value": value}

    def register_prompt(self, name: str, description: str, template: str, args: list[str]):
        self._prompts[name] = {
            "description": description,
            "template": template,
            "arguments": args,
        }

    # ── The single JSON-RPC gateway ──────────────────────────────────────────

    def handle(self, request: dict) -> dict:
        method = request.get("method", "")
        rid = request.get("id", 0)
        params = request.get("params") or {}

        if method == "initialize":
            return _jsonrpc_result(rid, {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": self.name, "version": "1.0.0"},
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
            })

        elif method == "tools/list":
            tools = [
                {"name": n, "description": d["description"], "inputSchema": d["inputSchema"]}
                for n, d in self._tools.items()
            ]
            return _jsonrpc_result(rid, {"tools": tools})

        elif method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments", {})
            if name not in self._tools:
                return _jsonrpc_error(rid, -32601, f"Tool '{name}' not found")
            try:
                result = self._tools[name]["fn"](**args)
                return _jsonrpc_result(rid, {"content": [{"type": "text", "text": str(result)}], "isError": False})
            except Exception as exc:
                return _jsonrpc_result(rid, {"content": [{"type": "text", "text": str(exc)}], "isError": True})

        elif method == "resources/list":
            resources = [
                {"uri": uri, "description": d["description"]}
                for uri, d in self._resources.items()
            ]
            return _jsonrpc_result(rid, {"resources": resources})

        elif method == "resources/read":
            uri = params.get("uri", "")
            if uri not in self._resources:
                return _jsonrpc_error(rid, -32601, f"Resource '{uri}' not found")
            value = self._resources[uri]["value"]
            text = _pretty(value) if not isinstance(value, str) else value
            return _jsonrpc_result(rid, {
                "contents": [{"uri": uri, "mimeType": "text/plain", "text": text}]
            })

        elif method == "prompts/list":
            prompts = [
                {"name": n, "description": d["description"],
                 "arguments": [{"name": a, "required": True} for a in d["arguments"]]}
                for n, d in self._prompts.items()
            ]
            return _jsonrpc_result(rid, {"prompts": prompts})

        elif method == "prompts/get":
            name = params.get("name", "")
            args = params.get("arguments", {})
            if name not in self._prompts:
                return _jsonrpc_error(rid, -32601, f"Prompt '{name}' not found")
            tpl = self._prompts[name]["template"]
            filled = tpl
            for k, v in args.items():
                filled = filled.replace(f"{{{k}}}", str(v))
            return _jsonrpc_result(rid, {
                "description": self._prompts[name]["description"],
                "messages": [{"role": "user", "content": {"type": "text", "text": filled}}],
            })

        elif method == "roots/list":
            # Roots: the SERVER calls this to ask the CLIENT what it may access
            return _jsonrpc_result(rid, {"roots": self._roots})

        elif method == "sampling/createMessage":
            # Sampling: server requests the client's LLM — handled in the demo layer
            return _jsonrpc_result(rid, {"__sampling_request__": True, "params": params})

        else:
            return _jsonrpc_error(rid, -32601, f"Unknown method: {method}")


# ── Build a shared demo server with all primitives registered ────────────────

server = MiniMCPServer("BankingMCPServer")

# Tools
server.register_tool(
    "get_account_balance",
    "Return the mock balance for a given account number.",
    {
        "type": "object",
        "properties": {"account_id": {"type": "string", "description": "Account number"}},
        "required": ["account_id"],
    },
    lambda account_id: f"Account {account_id}: Balance = ₹ {(hash(account_id) % 90000) + 10000:,}.00",
)
server.register_tool(
    "calculate_emi",
    "Calculate monthly EMI for a loan.",
    {
        "type": "object",
        "properties": {
            "principal": {"type": "number"},
            "annual_rate": {"type": "number", "description": "Annual interest rate (%)"},
            "months": {"type": "integer"},
        },
        "required": ["principal", "annual_rate", "months"],
    },
    lambda principal, annual_rate, months: (
        f"EMI = ₹ {principal * (annual_rate/1200) * (1 + annual_rate/1200)**months / ((1 + annual_rate/1200)**months - 1):,.2f} / month"
    ),
)

# Resources
server.register_resource(
    "bank://policies/kyc-rules",
    "KYC compliance rules document",
    "KYC Rules v3.2: 1) Govt-issued photo ID required. 2) Address proof mandatory. 3) PAN card for transactions > ₹50,000.",
)
server.register_resource(
    "bank://customers/C001/profile",
    "Customer profile for C001",
    {"id": "C001", "name": "Arjun Sharma", "tier": "Gold", "since": "2019-03-15", "branch": "Chennai-OMR"},
)

# Prompts
server.register_prompt(
    "summarize_account_activity",
    "Generate a summary prompt for a customer's recent account activity.",
    "Summarise the last {days} days of activity for account {account_id}. "
    "Highlight any unusual transactions, flag potential fraud, and recommend actions.",
    ["account_id", "days"],
)
server.register_prompt(
    "draft_loan_decision_letter",
    "Draft a formal loan decision letter.",
    "Draft a formal letter to customer {customer_name} regarding their loan application "
    "for ₹{loan_amount}. Decision: {decision}. Be professional and concise.",
    ["customer_name", "loan_amount", "decision"],
)


# ═══════════════════════════════════════════════════════════════════════════════
#  TRANSPORT DEMOS
# ═══════════════════════════════════════════════════════════════════════════════

# ── Transport 1: Standard IO ─────────────────────────────────────────────────

STDIO_SERVER_CODE = '''\
# stdio_demo_server.py
# This is a STANDALONE script that reads JSON-RPC from stdin, writes to stdout.
# The client (app.py) launches it as a subprocess — they communicate via pipes.

import sys, json
from datetime import datetime

TOOLS = [{
    "name": "get_current_datetime",
    "description": "Returns current date/time in the given strftime format.",
    "inputSchema": {
        "type": "object",
        "properties": {"date_format": {"type": "string"}},
        "required": ["date_format"],
    },
}]

def handle(req):
    m, rid, params = req.get("method"), req.get("id"), req.get("params") or {}
    if m == "initialize":
        res = {"protocolVersion": "2024-11-05",
               "serverInfo": {"name": "stdio-datetime", "version": "1.0.0"},
               "capabilities": {"tools": {}}}
    elif m == "tools/list":
        res = {"tools": TOOLS}
    elif m == "tools/call":
        fmt = (params.get("arguments") or {}).get("date_format", "%Y-%m-%d %H:%M:%S")
        res = {"content": [{"type": "text", "text": datetime.now().strftime(fmt)}], "isError": False}
    else:
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32601, "message": "Unknown method"}}
    return {"jsonrpc": "2.0", "id": rid, "result": res}

for line in sys.stdin:               # ← blocks waiting for each request
    line = line.strip()
    if not line:
        continue
    sys.stdout.write(json.dumps(handle(json.loads(line))) + "\\n")
    sys.stdout.flush()               # ← must flush or the pipe blocks
'''


def _write_stdio_server():
    path = "/tmp/stdio_demo_server.py"
    with open(path, "w") as f:
        f.write(STDIO_SERVER_CODE)
    return path


def run_stdio_demo(date_format: str) -> tuple[str, str, str]:
    """
    Launches a REAL subprocess, sends JSON-RPC over its stdin, reads stdout.
    Shows beginners the exact bytes that cross process boundaries.
    """
    path = _write_stdio_server()
    log = []

    try:
        proc = subprocess.Popen(
            [sys.executable, path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        def send(req: dict) -> dict:
            line = json.dumps(req) + "\n"
            log.append(("→ CLIENT sends (stdin):", _pretty(req)))
            proc.stdin.write(line)
            proc.stdin.flush()
            raw = proc.stdout.readline()
            resp = json.loads(raw)
            log.append(("← SERVER responds (stdout):", _pretty(resp)))
            return resp

        # Step 1: handshake
        send(_jsonrpc_request("initialize", {"protocolVersion": "2024-11-05",
                                              "clientInfo": {"name": "explorer"}}, 1))
        # Step 2: discover tools
        send(_jsonrpc_request("tools/list", {}, 2))
        # Step 3: call the tool
        send(_jsonrpc_request("tools/call",
                              {"name": "get_current_datetime",
                               "arguments": {"date_format": date_format}}, 3))
        proc.stdin.close()
        proc.wait(timeout=5)

    except Exception as exc:
        log.append(("ERROR", str(exc)))

    explanation = textwrap.dedent("""
    WHAT JUST HAPPENED — Standard IO (stdio) Transport
    ═══════════════════════════════════════════════════
    1. The CLIENT launched the server as a child process (subprocess.Popen).
    2. Every JSON-RPC message was written as one line of text to the server's STDIN pipe.
    3. The server read each line, processed it, and wrote one response line to STDOUT.
    4. The client read that response line back.

    ANALOGY: Two people in the same room passing written notes.

    WHY USE stdio?
    • Fastest — no network, no serialisation overhead beyond JSON.
    • Simplest — no auth, no ports, no firewall rules.
    • Best for LOCAL tools: file readers, local databases, code runners.
    • Claude Desktop uses stdio for all its built-in MCP servers.

    WHEN NOT TO USE stdio?
    • You need one server shared by many clients across the network → use HTTP.
    • You need real-time push from server to client → use WebSockets.
    """).strip()

    wire_log = "\n\n".join(f"{label}\n{msg}" for label, msg in log)
    return explanation, wire_log, f"✅ Done — used date_format: '{date_format}'"


# ── Transport 2: HTTP ────────────────────────────────────────────────────────

def run_http_demo(query: str) -> tuple[str, str, str]:
    """
    Simulates an HTTP-style MCP call.  We don't actually start a web server
    (that needs a free port & threads), but we show the exact HTTP envelope
    a real HTTP MCP client would POST and receive.

    The actual JSON-RPC is still processed by the in-process MiniMCPServer,
    letting beginners focus on the message shape, not network plumbing.
    """
    # Build the request as if it were an HTTP POST body
    req = _jsonrpc_request("tools/call",
                           {"name": "get_account_balance", "arguments": {"account_id": query}}, 1)

    http_request_envelope = textwrap.dedent(f"""\
    POST /mcp HTTP/1.1
    Host: api.mybank.com
    Content-Type: application/json
    Authorization: Bearer <token>

    {_pretty(req)}
    """)

    # Process through our in-process server (same JSON-RPC, different pipe)
    server.handle(_jsonrpc_request("initialize", {}, 0))  # init first
    resp = server.handle(req)

    http_response_envelope = textwrap.dedent(f"""\
    HTTP/1.1 200 OK
    Content-Type: application/json

    {_pretty(resp)}
    """)

    explanation = textwrap.dedent("""
    WHAT JUST HAPPENED — HTTP Transport
    ════════════════════════════════════
    1. The CLIENT built a JSON-RPC request and POSTed it to the server's URL.
    2. The SERVER processed the request and returned a JSON-RPC response in the HTTP body.
    3. For long operations, the server can STREAM partial results using Server-Sent Events (SSE).

    ANALOGY: Posting a letter to an address — you write the address (URL),
    seal the letter (JSON-RPC body), post it, and wait for a reply.

    WHY USE HTTP?
    • Works across the INTERNET — the server can be anywhere with a URL.
    • Standard web infrastructure: load balancers, auth tokens, TLS, logging.
    • Many clients can share ONE server simultaneously.
    • Best for HOSTED tools: cloud APIs, shared company services, SaaS integrations.

    WHEN NOT TO USE HTTP?
    • You need BI-DIRECTIONAL real-time messages — use WebSockets.
    • The server is local and you want zero overhead — use stdio.

    KEY POINT: The JSON-RPC 2.0 message inside the HTTP body is IDENTICAL to
    what stdio sends. Only the delivery envelope changes.
    """).strip()

    wire_log = (
        "── HTTP REQUEST (client → server) ──\n" + http_request_envelope +
        "\n── HTTP RESPONSE (server → client) ──\n" + http_response_envelope
    )
    return explanation, wire_log, f"✅ Balance fetched for account: '{query}'"


# ── Transport 3: WebSockets ──────────────────────────────────────────────────

def run_websocket_demo(topic: str) -> tuple[str, str, str]:
    """
    Simulates a WebSocket MCP session with multiple messages flowing both ways.
    We show what a REAL WebSocket conversation looks like — the persistent
    connection with both client and server sending at any time.
    """
    # Simulate a multi-turn WebSocket conversation
    conversation = []

    def ws_send(direction: str, payload: dict):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        conversation.append((ts, direction, _pretty(payload)))

    # Client connects and initialises
    init_req = _jsonrpc_request("initialize", {"protocolVersion": "2024-11-05",
                                               "clientInfo": {"name": "ws-explorer"}}, 1)
    ws_send("CLIENT → SERVER", init_req)
    init_resp = server.handle(init_req)
    ws_send("SERVER → CLIENT", init_resp)

    # Client discovers tools
    list_req = _jsonrpc_request("tools/list", {}, 2)
    ws_send("CLIENT → SERVER", list_req)
    list_resp = server.handle(list_req)
    ws_send("SERVER → CLIENT", list_resp)

    # Server PUSHES a notification (unique to WebSockets — no request needed!)
    ws_send("SERVER → CLIENT (PUSH — no request!)", {
        "jsonrpc": "2.0",
        "method": "notifications/tools/list_changed",
        "params": {"message": f"New tool added related to '{topic}' — please re-list!"},
    })

    # Client calls a tool
    call_req = _jsonrpc_request("tools/call",
                                {"name": "get_account_balance",
                                 "arguments": {"account_id": "ACC-WS-001"}}, 3)
    ws_send("CLIENT → SERVER", call_req)
    call_resp = server.handle(call_req)
    ws_send("SERVER → CLIENT", call_resp)

    explanation = textwrap.dedent("""
    WHAT JUST HAPPENED — WebSocket Transport
    ════════════════════════════════════════
    1. The CLIENT opened ONE persistent connection to the server (ws://...).
    2. Both sides can send messages at any time — no need to "ask first".
    3. The SERVER pushed a notification (the PUSH message) WITHOUT the client requesting it.
    4. The connection stays open for the entire session — no reconnecting per request.

    ANALOGY: A phone call left off the hook. Either person speaks whenever they want,
    without hanging up and dialling again.

    WHY USE WebSockets?
    • BIDIRECTIONAL: server can push alerts, events, progress — without polling.
    • REAL-TIME: live dashboards, streaming tool output, event-driven agents.
    • EFFICIENT: one connection, no HTTP handshake overhead per message.
    • Best for: live market data, real-time fraud alerts, streaming AI responses.

    NOTICE THE PUSH MESSAGE above — that's the killer feature of WebSockets.
    stdio and HTTP can't do that; the client always has to ask first.

    KEY POINT: Still the same JSON-RPC 2.0 envelope — just delivered over a
    persistent two-way channel instead of a one-shot pipe or HTTP request.
    """).strip()

    wire_log = ""
    for ts, direction, payload in conversation:
        wire_log += f"[{ts}]  {direction}\n{payload}\n\n"

    return explanation, wire_log, f"✅ WebSocket session completed for topic: '{topic}'"


# ═══════════════════════════════════════════════════════════════════════════════
#  PRIMITIVE DEMOS
# ═══════════════════════════════════════════════════════════════════════════════

# ── Primitive 1: Tools ───────────────────────────────────────────────────────

def run_tools_demo(account_id: str, principal: float, rate: float, months: int) -> tuple[str, str, str]:
    log = []

    # Step 1: discover
    list_req = _jsonrpc_request("tools/list", {}, 1)
    list_resp = server.handle(list_req)
    log.append(("tools/list request", _pretty(list_req)))
    log.append(("tools/list response", _pretty(list_resp)))

    # Step 2: call balance tool
    bal_req = _jsonrpc_request("tools/call",
                               {"name": "get_account_balance",
                                "arguments": {"account_id": account_id}}, 2)
    bal_resp = server.handle(bal_req)
    log.append(("tools/call → get_account_balance", _pretty(bal_req)))
    log.append(("tools/call ← result", _pretty(bal_resp)))

    # Step 3: call EMI tool
    emi_req = _jsonrpc_request("tools/call",
                               {"name": "calculate_emi",
                                "arguments": {"principal": principal,
                                              "annual_rate": rate,
                                              "months": months}}, 3)
    emi_resp = server.handle(emi_req)
    log.append(("tools/call → calculate_emi", _pretty(emi_req)))
    log.append(("tools/call ← result", _pretty(emi_resp)))

    bal_text = bal_resp["result"]["content"][0]["text"]
    emi_text = emi_resp["result"]["content"][0]["text"]

    explanation = textwrap.dedent("""
    PRIMITIVE 1: TOOLS  (model-controlled)
    ══════════════════════════════════════
    Tools are ACTIONS the AI can trigger — the VERBS of MCP.

    HOW IT WORKS:
      1. Client calls  tools/list  →  server returns every tool's name + JSON Schema.
      2. The AI (Claude) reads those schemas and decides WHICH tool to call and WHAT arguments to pass.
      3. Client calls  tools/call  →  server runs the function and returns the result.
      4. The AI reads the result and continues the conversation.

    WHY "model-controlled"?
      The MODEL (Claude) decides when to call a tool and with which arguments.
      The human doesn't pick the tool — the AI reasons about it.

    REAL BANKING EXAMPLES:
      • get_account_balance(account_id)
      • transfer_funds(from_acc, to_acc, amount)
      • flag_transaction_as_fraud(transaction_id)
      • calculate_emi(principal, rate, months)

    KEY RULE: Tools are for DOING things — they usually have side effects.
    If you just want to READ data, that's a Resource (Primitive 2).
    """).strip()

    wire_log = "\n\n".join(f"── {label} ──\n{msg}" for label, msg in log)
    summary = f"✅  {bal_text}\n✅  {emi_text}"
    return explanation, wire_log, summary


# ── Primitive 2: Resources ───────────────────────────────────────────────────

def run_resources_demo(uri: str) -> tuple[str, str, str]:
    log = []

    # Discover resources
    list_req = _jsonrpc_request("resources/list", {}, 1)
    list_resp = server.handle(list_req)
    log.append(("resources/list request", _pretty(list_req)))
    log.append(("resources/list response", _pretty(list_resp)))

    # Read a specific resource
    read_req = _jsonrpc_request("resources/read", {"uri": uri}, 2)
    read_resp = server.handle(read_req)
    log.append(("resources/read request", _pretty(read_req)))
    log.append(("resources/read response", _pretty(read_resp)))

    if "result" in read_resp:
        content = read_resp["result"]["contents"][0]["text"]
    else:
        content = str(read_resp.get("error", "Unknown error"))

    explanation = textwrap.dedent("""
    PRIMITIVE 2: RESOURCES  (app-controlled)
    ════════════════════════════════════════
    Resources are READ-ONLY DATA the server exposes — the NOUNS of MCP.

    HOW IT WORKS:
      1. Client calls  resources/list  →  server returns URIs + descriptions.
      2. Client calls  resources/read  with a URI  →  server returns the content.
      3. The content is injected into the AI's context (not "called" like a tool).

    WHY "app-controlled"?
      The APPLICATION decides which resources to fetch and when — not the AI.
      The AI reads the data passively; it can't trigger resource loading itself.

    URIs look like file paths or web addresses:
      • file:///policies/kyc-rules.pdf
      • bank://customers/C001/profile
      • db://transactions/last-30-days

    REAL BANKING EXAMPLES:
      • bank://policies/kyc-rules        →  KYC compliance document
      • bank://customers/C001/profile    →  Customer profile JSON
      • bank://rates/current             →  Today's interest rates
      • bank://reports/monthly-audit     →  Audit report PDF

    KEY DIFFERENCE FROM TOOLS:
      Tools = DO something (verb, side effect possible)
      Resources = READ something (noun, always read-only)
    """).strip()

    wire_log = "\n\n".join(f"── {label} ──\n{msg}" for label, msg in log)
    return explanation, wire_log, f"✅  Resource content:\n\n{content}"


# ── Primitive 3: Prompts ─────────────────────────────────────────────────────

def run_prompts_demo(prompt_name: str, arg1_key: str, arg1_val: str, arg2_key: str, arg2_val: str) -> tuple[str, str, str]:
    log = []

    # Discover prompts
    list_req = _jsonrpc_request("prompts/list", {}, 1)
    list_resp = server.handle(list_req)
    log.append(("prompts/list request", _pretty(list_req)))
    log.append(("prompts/list response", _pretty(list_resp)))

    # Get (fill in) the prompt
    arguments = {}
    if arg1_key and arg1_val:
        arguments[arg1_key] = arg1_val
    if arg2_key and arg2_val:
        arguments[arg2_key] = arg2_val

    get_req = _jsonrpc_request("prompts/get", {"name": prompt_name, "arguments": arguments}, 2)
    get_resp = server.handle(get_req)
    log.append(("prompts/get request", _pretty(get_req)))
    log.append(("prompts/get response", _pretty(get_resp)))

    if "result" in get_resp:
        filled_prompt = get_resp["result"]["messages"][0]["content"]["text"]
    else:
        filled_prompt = str(get_resp.get("error", "Check prompt name and arguments"))

    explanation = textwrap.dedent("""
    PRIMITIVE 3: PROMPTS  (user-controlled)
    ════════════════════════════════════════
    Prompts are REUSABLE TEMPLATES that shape how the AI is asked — saved slash-commands.

    HOW IT WORKS:
      1. Client calls  prompts/list  →  server returns available prompt templates.
      2. The USER picks a prompt (e.g. clicks "/summarize-account").
      3. Client calls  prompts/get  with the chosen name + arguments
         →  server fills in the template and returns ready-to-use messages.
      4. Those messages go straight to the AI — no manual prompt writing needed.

    WHY "user-controlled"?
      The USER (human) chooses which prompt to run, unlike Tools (model picks)
      or Resources (app picks). It appears as a slash-command or menu option.

    ANALOGY: Saved email templates — you pick the template, fill in {name}
    and {amount}, and the message is ready. No re-typing the structure each time.

    REAL BANKING EXAMPLES:
      /summarize-account-activity {account_id} {days}
      /draft-loan-decision-letter {customer_name} {amount} {decision}
      /generate-compliance-report {month} {branch}
      /create-fraud-alert {transaction_id}

    KEY BENEFIT: Standardises HOW tasks are asked across a team or product,
    so every agent or user follows the same best-practice prompt structure.
    """).strip()

    wire_log = "\n\n".join(f"── {label} ──\n{msg}" for label, msg in log)
    return explanation, wire_log, f"✅  Filled prompt ready for Claude:\n\n{filled_prompt}"


# ── Primitive 4: Sampling ────────────────────────────────────────────────────

def run_sampling_demo(text_to_summarize: str) -> tuple[str, str, str]:
    """
    Sampling: the SERVER asks the CLIENT's LLM to do some thinking.
    The server itself has no AI — it borrows the client's Claude.
    """
    log = []

    # Step 1: client calls a tool on the server
    call_req = _jsonrpc_request("tools/call",
                                {"name": "get_account_balance",
                                 "arguments": {"account_id": "ACC-SAMPLE"}}, 1)
    log.append(("Step 1 — Client calls a tool", _pretty(call_req)))

    # Step 2: server internally decides it needs AI reasoning, sends sampling request
    sampling_request = {
        "jsonrpc": "2.0",
        "id": 99,
        "method": "sampling/createMessage",
        "params": {
            "messages": [
                {"role": "user", "content": {"type": "text",
                                              "text": f"Please summarise the following in one sentence:\n\n{text_to_summarize}"}}
            ],
            "maxTokens": 200,
            "systemPrompt": "You are a concise financial analyst. Summarise clearly.",
        },
    }
    log.append(("Step 2 — Server sends sampling request TO the client (reverse!)", _pretty(sampling_request)))

    # Step 3: client fulfils the sampling request using its own Claude
    if _anthropic and _API_KEY:
        try:
            resp = _anthropic.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=200,
                messages=[{"role": "user",
                           "content": f"Please summarise the following in one sentence:\n\n{text_to_summarize}"}],
            )
            ai_answer = resp.content[0].text
        except Exception as exc:
            ai_answer = f"[API call failed — using mock] Summary: '{text_to_summarize[:60]}...'"
    else:
        ai_answer = f"[No API key — mock response] Summary: The text discusses '{text_to_summarize[:50]}...' in a financial context."

    sampling_response = _jsonrpc_result(99, {
        "role": "assistant",
        "content": {"type": "text", "text": ai_answer},
        "model": "claude-sonnet-4-6",
        "stopReason": "end_turn",
    })
    log.append(("Step 3 — Client returns Claude's answer TO the server", _pretty(sampling_response)))

    # Step 4: server returns the final tool result to the client
    final_result = _jsonrpc_result(1, {
        "content": [{"type": "text", "text": f"Summary (produced by client's Claude): {ai_answer}"}],
        "isError": False,
    })
    log.append(("Step 4 — Server returns final tool result (containing AI output)", _pretty(final_result)))

    explanation = textwrap.dedent("""
    PRIMITIVE 4: SAMPLING  (server asks client)  ← REVERSE DIRECTION!
    ══════════════════════════════════════════════════════════════════
    Sampling lets the SERVER borrow the CLIENT's LLM instead of embedding its own.

    THE FLOW (read the wire log carefully — it's a round-trip inside a round-trip):
      1. Client calls a tool on the server  (normal, left-to-right).
      2. Server realises it needs AI reasoning → sends  sampling/createMessage  TO the client.
      3. Client receives this, calls ITS OWN Claude with those messages.
      4. Client returns Claude's answer to the server.
      5. Server uses that answer to complete the original tool call.

    ANALOGY: You hire a contractor (server) to write a report. The contractor
    says "I need a lawyer to review one clause — can you call your lawyer for me?"
    You make the call, relay the answer. The contractor finishes the report.

    WHY THIS MATTERS:
      • The server ships ZERO model config, ZERO API key, ZERO billing.
      • The same MCP server runs in Claude Desktop, VS Code, your app — each
        host supplies its own model. Server describes the TASK; client owns the MODEL.
      • Enables agent-in-agent: a tool can itself reason, without every tool
        needing to embed a full LLM stack.

    SECURITY: The client always controls whether to fulfil a sampling request —
    it can refuse, rate-limit, or substitute a different model.
    """).strip()

    wire_log = "\n\n".join(f"── {label} ──\n{msg}" for label, msg in log)
    return explanation, wire_log, f"✅  Sampling complete.\n\nAI summary:\n{ai_answer}"


# ── Primitive 5: Roots ───────────────────────────────────────────────────────

def run_roots_demo(root1: str, root2: str) -> tuple[str, str, str]:
    """
    Roots: the client declares the folders/URIs the server is allowed to operate within.
    The server can ask for this list; the client is the authority.
    """
    log = []

    # Simulate: client registers roots before connecting
    declared_roots = [r.strip() for r in [root1, root2] if r.strip()]
    server._roots = [{"uri": r, "name": r.split("/")[-1] or r} for r in declared_roots]

    # Server asks: what am I allowed to touch?
    roots_req = _jsonrpc_request("roots/list", {}, 1)
    log.append(("Server asks the client: roots/list", _pretty(roots_req)))
    roots_resp = server.handle(roots_req)
    log.append(("Client answers with its declared roots", _pretty(roots_resp)))

    # Simulate: server tries to work inside an allowed root
    allowed = declared_roots[0] if declared_roots else "none"
    access_log = {
        "server_attempted_to_access": f"{allowed}/transactions/2025.csv",
        "is_within_roots": True,
        "action": "ALLOWED — path is inside a declared root",
    }
    log.append(("Server checks: is this path inside my roots?", _pretty(access_log)))

    # Simulate: server tries to work OUTSIDE declared roots
    denied_log = {
        "server_attempted_to_access": "/etc/passwords",
        "is_within_roots": False,
        "action": "DENIED — path is NOT in any declared root",
    }
    log.append(("Server checks: is this path inside my roots?", _pretty(denied_log)))

    explanation = textwrap.dedent("""
    PRIMITIVE 5: ROOTS  (client-controlled)  ← CLIENT SETS THE FENCE
    ══════════════════════════════════════════════════════════════════
    Roots are the SCOPE BOUNDARIES the client declares for the server.
    The client decides WHERE the server is allowed to operate.

    HOW IT WORKS:
      1. Before connecting, the CLIENT sets a list of allowed URIs (folders, URLs).
      2. The SERVER can call  roots/list  to ask "what am I allowed to access?".
      3. A well-behaved server STAYS INSIDE those roots — it never reaches beyond.
      4. The client is the SOLE AUTHORITY on what roots are granted.

    ANALOGY: You hire a cleaner (server) and give them keys to the living room
    and kitchen — but NOT the bedroom or office. They can only clean where the
    keys work. You (the client) decide which rooms they get keys to.

    URI EXAMPLES:
      file:///home/user/project        →  local folder
      file:///home/user/shared         →  shared folder
      https://api.mybank.com/data      →  remote API base URL
      git://github.com/org/repo        →  a specific repo

    WHY THIS MATTERS — SECURITY:
      • Enforces LEAST PRIVILEGE: the server is powerful but scoped.
      • A filesystem server can't read /etc/passwords if that's not in roots.
      • A GitHub server can't touch repos outside the declared list.
      • Security lives on the CLIENT side, where the human (or company policy) controls it.

    THE PATTERN: Capability lives on the server. Authority lives on the client.
    """).strip()

    wire_log = "\n\n".join(f"── {label} ──\n{msg}" for label, msg in log)
    granted = "\n".join(f"  ✅  {r}" for r in declared_roots) or "  (none declared)"
    return explanation, wire_log, f"Roots granted to server:\n{granted}\n\n✅ Access control enforced."


# ═══════════════════════════════════════════════════════════════════════════════
#  GRADIO UI
# ═══════════════════════════════════════════════════════════════════════════════

_CONCEPT_CSS = """
.concept-box {
    background: #e9f5f4;
    border-left: 4px solid #028090;
    padding: 14px 18px;
    border-radius: 0 8px 8px 0;
    font-family: monospace;
    font-size: 13px;
    white-space: pre-wrap;
}
"""

def _code_block(text: str) -> str:
    """Wrap text in a markdown code block for display."""
    return f"```\n{text}\n```"


# ── Shared output column layout ───────────────────────────────────────────────

def _output_cols():
    with gr.Row():
        with gr.Column(scale=1):
            explanation = gr.Textbox(label="📖 Concept Explanation",
                                     lines=20, interactive=False,
                                     elem_classes=["concept-box"])
        with gr.Column(scale=1):
            wire = gr.Textbox(label="🔌 Raw JSON-RPC Wire Messages",
                              lines=20, interactive=False)
    result = gr.Textbox(label="✅ Result / Summary", lines=3, interactive=False)
    return explanation, wire, result


with gr.Blocks(
    title="MCP Explorer — Transports & Primitives",
) as demo:

    gr.Markdown("""
# 🌐 MCP Explorer — Transports & Primitives
### Interactive demos for beginner learners | Teal Trust Workshop

**The big idea:** MCP uses one standard wire format — **JSON-RPC 2.0** — carried over different
*transports* (how it travels) to deliver five *primitives* (what it carries).

- **Tabs 1–3**: Three transports — *stdio*, *HTTP*, *WebSocket*
- **Tabs 4–8**: Five primitives — *Tools*, *Resources*, *Prompts*, *Sampling*, *Roots*

👉 **Click any tab, fill in the inputs, and press Run.**  Every demo shows you the raw JSON-RPC
messages alongside a plain-English explanation.
""")

    # ══ TAB 1: stdio ══════════════════════════════════════════════════════════
    with gr.Tab("1️⃣  stdio Transport"):
        gr.Markdown("""
## Standard IO Transport
**The pipe is two text streams**: the client writes JSON to the server's **stdin**,
the server writes JSON back to its **stdout**.  No network.  No port.  Fastest.

The server below runs as a **real subprocess** — watch the process boundary in the wire log.
        """)
        with gr.Row():
            date_fmt = gr.Textbox(
                label="Date format string (Python strftime)",
                value="%d %B %Y — %I:%M %p",
                placeholder="%Y-%m-%d %H:%M:%S",
            )
            run_stdio = gr.Button("▶  Run stdio Demo", variant="primary")

        # Show the server source so beginners can read it
        with gr.Accordion("📄 Server source code (stdio_demo_server.py — runs in a real subprocess)", open=False):
            gr.Code(value=STDIO_SERVER_CODE, language="python")

        explanation_1, wire_1, result_1 = _output_cols()
        run_stdio.click(
            fn=run_stdio_demo,
            inputs=[date_fmt],
            outputs=[explanation_1, wire_1, result_1],
        )

    # ══ TAB 2: HTTP ═══════════════════════════════════════════════════════════
    with gr.Tab("2️⃣  HTTP Transport"):
        gr.Markdown("""
## HTTP Transport
The server lives at a **URL**.  The client sends an HTTP **POST** request; the server
replies with a JSON body.  The JSON-RPC envelope is identical — only the delivery changes.

Try different account IDs to see how the same tool call travels over HTTP.
        """)
        with gr.Row():
            acct_id = gr.Textbox(
                label="Account ID to query",
                value="ACC-BANK-001",
                placeholder="ACC-BANK-001",
            )
            run_http = gr.Button("▶  Run HTTP Demo", variant="primary")

        explanation_2, wire_2, result_2 = _output_cols()
        run_http.click(
            fn=run_http_demo,
            inputs=[acct_id],
            outputs=[explanation_2, wire_2, result_2],
        )

    # ══ TAB 3: WebSockets ═════════════════════════════════════════════════════
    with gr.Tab("3️⃣  WebSocket Transport"):
        gr.Markdown("""
## WebSocket Transport
ONE persistent connection stays open.  Both client and server can send messages **at any time**.
Notice the **PUSH** message in the wire log — the server sends it without being asked.
That's the feature only WebSockets has.
        """)
        with gr.Row():
            topic = gr.Textbox(
                label="Topic (used in the server push notification)",
                value="FX rates",
                placeholder="e.g. interest rates, fraud alerts...",
            )
            run_ws = gr.Button("▶  Run WebSocket Demo", variant="primary")

        explanation_3, wire_3, result_3 = _output_cols()
        run_ws.click(
            fn=run_websocket_demo,
            inputs=[topic],
            outputs=[explanation_3, wire_3, result_3],
        )

    # ══ TAB 4: Tools ══════════════════════════════════════════════════════════
    with gr.Tab("4️⃣  Tools Primitive"):
        gr.Markdown("""
## Tools — the VERBS of MCP  *(model-controlled)*
Tools are **actions** the AI can trigger.  The model reads `tools/list`, decides what to call,
and sends `tools/call` with the right arguments.  Think: buttons the AI presses.
        """)
        with gr.Row():
            t_account = gr.Textbox(label="Account ID", value="ACC-JPM-2025")
            t_principal = gr.Number(label="Loan Principal (₹)", value=500000)
            t_rate = gr.Number(label="Annual Interest Rate (%)", value=8.5)
            t_months = gr.Number(label="Tenure (months)", value=60, precision=0)
        run_tools = gr.Button("▶  Run Tools Demo", variant="primary")

        explanation_4, wire_4, result_4 = _output_cols()
        run_tools.click(
            fn=run_tools_demo,
            inputs=[t_account, t_principal, t_rate, t_months],
            outputs=[explanation_4, wire_4, result_4],
        )

    # ══ TAB 5: Resources ══════════════════════════════════════════════════════
    with gr.Tab("5️⃣  Resources Primitive"):
        gr.Markdown("""
## Resources — the NOUNS of MCP  *(app-controlled)*
Resources are **read-only data** the server exposes via URIs.  The application fetches them
to give the AI context.  The AI reads; it doesn't trigger resources.
        """)
        with gr.Row():
            r_uri = gr.Dropdown(
                label="Resource URI to read",
                choices=[
                    "bank://policies/kyc-rules",
                    "bank://customers/C001/profile",
                ],
                value="bank://policies/kyc-rules",
            )
            run_resources = gr.Button("▶  Run Resources Demo", variant="primary")

        explanation_5, wire_5, result_5 = _output_cols()
        run_resources.click(
            fn=run_resources_demo,
            inputs=[r_uri],
            outputs=[explanation_5, wire_5, result_5],
        )

    # ══ TAB 6: Prompts ════════════════════════════════════════════════════════
    with gr.Tab("6️⃣  Prompts Primitive"):
        gr.Markdown("""
## Prompts — TEMPLATES the user picks  *(user-controlled)*
Prompts are slash-commands or menu options that return filled-in message templates.
The **user** selects a prompt; the server fills in the `{placeholders}` with the arguments.
        """)
        with gr.Row():
            p_name = gr.Dropdown(
                label="Prompt name",
                choices=["summarize_account_activity", "draft_loan_decision_letter"],
                value="summarize_account_activity",
            )
        with gr.Row():
            p_k1 = gr.Textbox(label="Argument 1 — Key", value="account_id")
            p_v1 = gr.Textbox(label="Argument 1 — Value", value="ACC-JPM-2025")
            p_k2 = gr.Textbox(label="Argument 2 — Key", value="days")
            p_v2 = gr.Textbox(label="Argument 2 — Value", value="30")
        run_prompts = gr.Button("▶  Run Prompts Demo", variant="primary")

        explanation_6, wire_6, result_6 = _output_cols()
        run_prompts.click(
            fn=run_prompts_demo,
            inputs=[p_name, p_k1, p_v1, p_k2, p_v2],
            outputs=[explanation_6, wire_6, result_6],
        )

    # ══ TAB 7: Sampling ═══════════════════════════════════════════════════════
    with gr.Tab("7️⃣  Sampling Primitive"):
        gr.Markdown("""
## Sampling — server BORROWS the client's AI  *(reverse direction)*
The server asks the **client's** LLM to do some reasoning.  The server ships no model,
no API key — it delegates thinking to whoever is on the client end.

*If `ANTHROPIC_API_KEY` is set, this calls real Claude.  Otherwise a mock is used.*
        """)
        sample_text = gr.Textbox(
            label="Text for the server to ask Claude to summarise",
            value=(
                "The Model Context Protocol (MCP) standardises how AI applications connect "
                "to external tools and data sources. It uses JSON-RPC 2.0 and defines five "
                "primitives: Tools, Resources, Prompts, Sampling, and Roots. Any MCP-compatible "
                "client can work with any MCP-compatible server without custom integration code."
            ),
            lines=4,
        )
        run_sampling = gr.Button("▶  Run Sampling Demo", variant="primary")

        explanation_7, wire_7, result_7 = _output_cols()
        run_sampling.click(
            fn=run_sampling_demo,
            inputs=[sample_text],
            outputs=[explanation_7, wire_7, result_7],
        )

    # ══ TAB 8: Roots ══════════════════════════════════════════════════════════
    with gr.Tab("8️⃣  Roots Primitive"):
        gr.Markdown("""
## Roots — the client sets the SCOPE FENCE  *(client-controlled)*
The client tells the server which folders or URLs it may operate within.
The server asks for this list; the client is the sole authority.  Security lives on the client side.
        """)
        with gr.Row():
            root1 = gr.Textbox(label="Root URI 1", value="file:///home/user/project")
            root2 = gr.Textbox(label="Root URI 2", value="file:///home/user/shared")
        run_roots = gr.Button("▶  Run Roots Demo", variant="primary")

        explanation_8, wire_8, result_8 = _output_cols()
        run_roots.click(
            fn=run_roots_demo,
            inputs=[root1, root2],
            outputs=[explanation_8, wire_8, result_8],
        )

    # ══ Summary cheat sheet ═══════════════════════════════════════════════════
    with gr.Tab("📋  Quick Reference"):
        gr.Markdown("""
## MCP Transports & Primitives — One-Page Cheat Sheet

### 🔌 Three Transports (the PIPE)

| Transport | Where's the server? | Direction | Best for |
|---|---|---|---|
| **stdio** | Same machine (subprocess) | Request → Reply | Local tools, Claude Desktop |
| **HTTP** | Remote URL | Request → Reply (can stream) | Hosted/shared services |
| **WebSocket** | Remote URL | Both sides, anytime | Real-time push, live alerts |

> The **JSON-RPC 2.0 message is identical** in all three. Only how it travels changes.

---

### 🧩 Five Primitives (what FLOWS through the pipe)

| # | Primitive | Direction | Controlled by | One-liner | Analogy |
|---|---|---|---|---|---|
| 1 | **Tools** | client → server | 🤖 Model | "Do this action" | Buttons the AI presses |
| 2 | **Resources** | client → server | 🖥️ App | "Read this data" | Files in a shared folder |
| 3 | **Prompts** | client → server | 👤 User | "Run this template" | Saved email templates |
| 4 | **Sampling** | server → client | 🔄 Server asks | "Borrow your AI" | Contractor uses your phone |
| 5 | **Roots** | server → client | 🔒 Client declares | "Here's your fence" | Keys to specific rooms |

---

### 🏦 Banking Examples

```
Tools     →  get_account_balance(account_id)
              flag_transaction_as_fraud(txn_id)
              calculate_emi(principal, rate, months)

Resources →  bank://policies/kyc-rules
              bank://customers/C001/profile
              bank://rates/current

Prompts   →  /summarize-account-activity {account_id} {days}
              /draft-loan-decision-letter {name} {amount} {decision}

Sampling  →  Server asks: "Summarise this transaction narrative for me"
              Client answers with Claude's response — server has no own API key

Roots     →  file:///home/analyst/approved-reports   ✅ allowed
              /etc/passwords                           ❌ NOT in roots — denied
```

---

### 📐 The Golden Rule

```
Transport = HOW the message travels
Primitive = WHAT the message carries

Both use the same JSON-RPC 2.0 envelope.
Pick the transport based on where the server lives and how live the session needs to be.
```
""")

# ── Launch ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "═" * 60)
    print("  MCP Explorer — Transports & Primitives")
    print("  Teal Trust Workshop Tool")
    print("═" * 60)
    if not _API_KEY:
        print("\n  ⚠️  No ANTHROPIC_API_KEY found in .env")
        print("     Sampling tab will use a mock response.")
        print("     All other tabs work without an API key.")
    else:
        print(f"\n  ✅ API key found — Sampling tab will call real Claude.")
    # Find a free port BEFORE calling launch so we only ever call it once.
    # Calling launch() twice (try/except) leaves the demo in a broken state.
    def _free_port(start: int = 7860) -> int:
        # Must check on 0.0.0.0 — the same address Gradio binds on.
        # On Windows, 127.0.0.1 and 0.0.0.0 are independent; a port can be
        # free on 127.0.0.1 but already occupied on 0.0.0.0.
        for p in range(start, start + 100):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
                    s.bind(("0.0.0.0", p))
                    return p
            except OSError:
                continue
        return start  # last resort

    port = _free_port(int(os.getenv("GRADIO_SERVER_PORT", "7860")))
    print(f"\n  Opening http://localhost:{port}\n")

    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        inbrowser=True,
        show_error=True,
        share=False,
        theme=gr.themes.Soft(primary_hue="teal"),
        css=_CONCEPT_CSS,
    )
