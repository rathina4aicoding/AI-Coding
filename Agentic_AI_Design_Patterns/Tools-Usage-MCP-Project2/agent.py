"""
agent.py  —  ReAct agentic loop that drives one or more MCP servers.

FLOW (ReAct over MCP):
  1. Discover tools from each MCP server (tools/list).
  2. Convert MCP tool schemas -> Anthropic tools[] format.
  3. Send user question + tools to Claude.
  4. On stop_reason='tool_use': route each tool_use block to the server that
     owns it (multi-server orchestration), call tools/call, return tool_result.
  5. Repeat until end_turn. Returns answer + a human-readable step log.

Also includes:
  - run_remote_mcp(): Pattern 2, Anthropic beta MCP connector (remote server).
  - mcp_sampling_demo(): Pattern 6, server-initiated LLM call (sampling).
"""
import os, json, time
import anthropic

_client = None
def client():
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY", "")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client

MAX_ITERS = 8

def mcp_tools_to_anthropic(mcp_clients):
    """Build Anthropic tools[] and a name->client routing map from MCP servers."""
    tools, route = [], {}
    for mc in mcp_clients:
        for t in mc.list_tools():
            tools.append({"name": t["name"], "description": t["description"],
                          "input_schema": t["inputSchema"]})
            route[t["name"]] = mc
    return tools, route

def run_agent(question, model, mcp_clients, system=None):
    """ReAct loop across one or more MCP servers. Returns dict with answer+log."""
    tools, route = mcp_tools_to_anthropic(mcp_clients)
    messages = [{"role": "user", "content": question}]
    log = []
    usage = {"input_tokens": 0, "output_tokens": 0}
    answer = ""
    sys_prompt = system or ("You are a helpful assistant. Use the available MCP "
                            "tools when they give better or real-time data. "
                            "Explain briefly which tool you use and why.")

    for _ in range(MAX_ITERS):
        resp = client().messages.create(
            model=model, max_tokens=1500, system=sys_prompt,
            tools=tools if tools else [], messages=messages)
        usage["input_tokens"]  += resp.usage.input_tokens
        usage["output_tokens"] += resp.usage.output_tokens

        for b in resp.content:
            if b.type == "text" and b.text.strip():
                log.append(("thought", b.text.strip()))
                answer = b.text.strip()

        if resp.stop_reason != "tool_use":
            break

        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for b in resp.content:
            if b.type != "tool_use":
                continue
            mc = route.get(b.name)
            srv_name = mc.name if mc else "?"
            log.append(("action", f"call {b.name} on [{srv_name}]  args={json.dumps(b.input)}"))
            if mc is None:
                out = json.dumps({"error": f"no server owns tool {b.name}"})
            else:
                out = mc.call_tool(b.name, b.input)
            log.append(("observation", out))
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": out})
        messages.append({"role": "user", "content": results})

    cost = usage["input_tokens"]/1e6*3 + usage["output_tokens"]/1e6*15
    return {"answer": answer, "log": log, "usage": usage, "cost_usd": round(cost, 6)}

# ---------------- PATTERN 2: remote MCP connector (beta) ----------------
def run_remote_mcp(question, model, server_url, token=None):
    """
    Anthropic beta MCP connector. Claude connects to a REMOTE MCP server
    server-side: it discovers + calls tools without your code proxying them.
    """
    if not server_url:
        return {"answer": "No REMOTE_MCP_URL configured. Set it in .env to try a "
                          "live remote MCP server (e.g. a public registry server).",
                "log": [("info", "Remote MCP demo skipped — no URL set.")],
                "usage": {}, "cost_usd": 0}
    mcp_server = {"type": "url", "url": server_url, "name": "remote-mcp"}
    if token:
        mcp_server["authorization_token"] = token
    try:
        resp = client().beta.messages.create(
            model=model, max_tokens=1200,
            messages=[{"role": "user", "content": question}],
            mcp_servers=[mcp_server],
            betas=["mcp-client-2025-11-20"])
        answer = " ".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return {"answer": answer or "(no text)",
                "log": [("info", f"Connected to remote MCP: {server_url}"),
                        ("observation", "Tool discovery + calls handled server-side by Anthropic.")],
                "usage": {"input_tokens": resp.usage.input_tokens,
                          "output_tokens": resp.usage.output_tokens},
                "cost_usd": 0}
    except Exception as e:
        return {"answer": f"Remote MCP error: {e}",
                "log": [("info", f"Failed to reach {server_url}: {e}")],
                "usage": {}, "cost_usd": 0}

# ---------------- PATTERN 6: sampling (server-initiated LLM call) ----------------
def mcp_sampling_demo(text_to_summarise, model):
    """
    Sampling = the MCP SERVER asks the CLIENT to run an LLM completion as part
    of executing a tool. Wire shape (server -> client):
        {"method":"sampling/createMessage",
         "params":{"messages":[...],"maxTokens":...}}
    Here we simulate that round-trip: the 'server' hands back a request, and
    the client (us) fulfils it with a real Claude call.
    """
    sampling_request = {
        "method": "sampling/createMessage",
        "params": {
            "messages": [{"role": "user",
                          "content": {"type": "text",
                                      "text": f"Summarise in one sentence: {text_to_summarise}"}}],
            "maxTokens": 100,
            "modelPreferences": {"hints": [{"name": model}]}}}
    log = [("action", "SERVER -> CLIENT  sampling/createMessage"),
           ("observation", json.dumps(sampling_request, indent=2))]
    try:
        resp = client().messages.create(
            model=model, max_tokens=120,
            messages=[{"role": "user",
                       "content": sampling_request["params"]["messages"][0]["content"]["text"]}])
        summary = " ".join(b.text for b in resp.content if b.type == "text")
        log.append(("thought", "CLIENT fulfils the sampling request with a real Claude call."))
        log.append(("observation", f"CLIENT -> SERVER  result: {summary}"))
        return {"answer": summary, "log": log,
                "usage": {"input_tokens": resp.usage.input_tokens,
                          "output_tokens": resp.usage.output_tokens},
                "cost_usd": 0}
    except Exception as e:
        return {"answer": f"Sampling error: {e}", "log": log, "usage": {}, "cost_usd": 0}
