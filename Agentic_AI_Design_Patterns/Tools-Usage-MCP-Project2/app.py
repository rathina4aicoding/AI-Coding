"""
app.py  —  Gradio UI for the MCP Server Patterns demo.
Run:  python app.py     (then open http://localhost:7860)

8 pattern tabs + Compare + Server Status. Every tab shows the MCP wire trace.
"""
import os, json, time, atexit
from dotenv import load_dotenv
load_dotenv()

import gradio as gr
from mcp_client import MCPClient
from db_seed import seed
import agent

# Seed banking DB at startup
seed()

MODELS = ["claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5"]
HERE = os.path.dirname(os.path.abspath(__file__))
def sp(name): return os.path.join(HERE, "mcp_servers", name)

# ---- Long-lived MCP clients (started lazily, reused across calls) ----
CLIENTS = {}
def get_client(key, path, env_extra=None):
    c = CLIENTS.get(key)
    if c is None or not c.is_alive():
        c = MCPClient(path, env_extra=env_extra, name=key).start()
        CLIENTS[key] = c
    return c

@atexit.register
def _cleanup():
    for c in CLIENTS.values():
        try: c.stop()
        except Exception: pass

# ---- Trace formatting ----
def fmt_wire(client):
    """Render the JSON-RPC wire trace of an MCP client."""
    if not client or not client.trace:
        return "_No MCP messages yet._"
    out = []
    for entry in client.trace[-40:]:
        arrow = "CLIENT --> SERVER" if entry["dir"] == "->" else "SERVER --> CLIENT"
        out.append(f"**{arrow}**\n```json\n{json.dumps(entry['msg'], indent=2)}\n```")
    return "\n".join(out)

def fmt_log(log):
    icons = {"thought": "THINK", "action": "ACT", "observation": "OBSERVE",
             "info": "INFO"}
    out = []
    for kind, content in log:
        c = content
        if kind == "observation":
            try: c = "```json\n" + json.dumps(json.loads(content), indent=2) + "\n```"
            except Exception: c = f"```\n{content}\n```"
        out.append(f"**{icons.get(kind, kind.upper())}**  {c if kind!='observation' else ''}\n{c if kind=='observation' else ''}")
    return "\n\n".join(out)

def fmt_usage(usage, cost):
    if not usage: return ""
    return (f"Tokens in/out: {usage.get('input_tokens',0):,} / "
            f"{usage.get('output_tokens',0):,}  ·  est. cost ~${cost:.5f}")

def need_key():
    return not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY"))

# ============================================================
# Pattern runners
# ============================================================
def run_p1(q, model):
    if need_key(): yield "Set ANTHROPIC_API_KEY or CLAUDE_API_KEY in .env", ""; return
    c = get_client("general", sp("general_server.py")); c.clear_trace()
    yield "Running...", ""
    r = agent.run_agent(q, model, [c])
    yield f"### Answer\n{r['answer']}\n\n*{fmt_usage(r['usage'],r['cost_usd'])}*\n\n---\n#### Agent steps\n{fmt_log(r['log'])}", fmt_wire(c)

def run_p2(q, model):
    if need_key(): yield "Set ANTHROPIC_API_KEY or CLAUDE_API_KEY in .env", ""; return
    url = os.environ.get("REMOTE_MCP_URL", ""); tok = os.environ.get("REMOTE_MCP_TOKEN", "")
    yield "Running...", ""
    r = agent.run_remote_mcp(q, model, url, tok)
    yield f"### Answer\n{r['answer']}\n\n*{fmt_usage(r['usage'],r['cost_usd'])}*", fmt_log(r['log'])

def run_p3(q, model):
    if need_key(): yield "Set ANTHROPIC_API_KEY or CLAUDE_API_KEY in .env", ""; return
    gen  = get_client("general", sp("general_server.py")); gen.clear_trace()
    math = get_client("math", sp("math_server.py")); math.clear_trace()
    yield "Running (2 servers)...", ""
    r = agent.run_agent(q, model, [gen, math])
    trace = "### general-server\n" + fmt_wire(gen) + "\n\n### math-server\n" + fmt_wire(math)
    yield f"### Answer\n{r['answer']}\n\n*{fmt_usage(r['usage'],r['cost_usd'])}*\n\n---\n#### Orchestration steps\n{fmt_log(r['log'])}", trace

def run_p4(uri):
    c = get_client("general", sp("general_server.py")); c.clear_trace()
    data = c.read_resource(uri)
    return f"### Resource: `{uri}`\n```\n{data}\n```\n\n*A resource is a DECLARATIVE data pull (like GET) — no action, no side effect, unlike a tool.*", fmt_wire(c)

def run_p5(template, topic, audience):
    c = get_client("general", sp("general_server.py")); c.clear_trace()
    args = {"topic": topic} if not audience else {"topic": topic, "audience": audience}
    rendered = c.get_prompt(template, args)
    out = f"### Rendered prompt from template `{template}`\n```\n{rendered}\n```"
    if not need_key():
        r = agent.run_agent(rendered, "claude-sonnet-4-6", [])
        out += f"\n\n### Claude's response\n{r['answer']}"
    return out, fmt_wire(c)

def run_p6(text, model):
    if need_key(): return "Set ANTHROPIC_API_KEY or CLAUDE_API_KEY in .env", ""
    r = agent.mcp_sampling_demo(text, model)
    return f"### Sampling result\n{r['answer']}\n\n*{fmt_usage(r['usage'],r['cost_usd'])}*", fmt_log(r['log'])

def run_p7(mode, q, model):
    if need_key(): yield "Set ANTHROPIC_API_KEY or CLAUDE_API_KEY in .env", ""; return
    key = f"stateful_{mode}"
    c = get_client(key, sp("stateful_server.py"), env_extra={"MCP_MODE": mode}); c.clear_trace()
    yield f"Running in {mode} mode...", ""
    r = agent.run_agent(q, model, [c],
        system=f"You are testing a {mode} MCP server. First set the current "
               f"customer to C-1001, then ask who the current customer is. "
               f"Report what happened.")
    yield f"### Answer ({mode})\n{r['answer']}\n\n*{fmt_usage(r['usage'],r['cost_usd'])}*\n\n---\n{fmt_log(r['log'])}", fmt_wire(c)

def run_p8(q, model):
    if need_key(): yield "Set ANTHROPIC_API_KEY or CLAUDE_API_KEY in .env", ""; return
    c = get_client("banking", sp("banking_server.py")); c.clear_trace()
    yield "Running banking query...", ""
    r = agent.run_agent(q, model, [c],
        system="You are a banking assistant. Use the banking MCP tools to answer. "
               "Be precise with figures and cite the customer_id.")
    yield f"### Answer\n{r['answer']}\n\n*{fmt_usage(r['usage'],r['cost_usd'])}*\n\n---\n#### Steps\n{fmt_log(r['log'])}", fmt_wire(c)

def run_compare(q, model):
    if need_key(): yield "Set ANTHROPIC_API_KEY in .env"; return
    yield "Running 3 patterns..."
    rows = []
    # P1 general, P3 multi, P8 banking
    gen = get_client("general", sp("general_server.py")); gen.clear_trace()
    r1 = agent.run_agent(q, model, [gen])
    math = get_client("math", sp("math_server.py")); math.clear_trace(); gen.clear_trace()
    r3 = agent.run_agent(q, model, [gen, math])
    bank = get_client("banking", sp("banking_server.py")); bank.clear_trace()
    r8 = agent.run_agent(q, model, [bank])
    table = ("| Pattern | Answer (short) | In tok | Out tok | Cost |\n|---|---|---|---|---|\n"
        f"| P1 Single server | {r1['answer'][:60]}... | {r1['usage'].get('input_tokens',0)} | {r1['usage'].get('output_tokens',0)} | ${r1['cost_usd']:.5f} |\n"
        f"| P3 Multi-server | {r3['answer'][:60]}... | {r3['usage'].get('input_tokens',0)} | {r3['usage'].get('output_tokens',0)} | ${r3['cost_usd']:.5f} |\n"
        f"| P8 Banking | {r8['answer'][:60]}... | {r8['usage'].get('input_tokens',0)} | {r8['usage'].get('output_tokens',0)} | ${r8['cost_usd']:.5f} |\n")
    yield "### Compare patterns 1, 3, 8 on the same question\n\n" + table

def server_status():
    if not CLIENTS:
        return "_No MCP servers started yet. Run any pattern tab first._"
    rows = ["| Server | Alive | PID | Uptime (s) | Tools | Resources | Prompts |",
            "|---|---|---|---|---|---|---|"]
    for key, c in CLIENTS.items():
        if c.is_alive():
            nt = len(c.list_tools()); nr = len(c.list_resources()); npr = len(c.list_prompts())
            rows.append(f"| {key} | yes | {c.pid} | {c.uptime} | {nt} | {nr} | {npr} |")
        else:
            rows.append(f"| {key} | no | - | - | - | - | - |")
    return "\n".join(rows)

# ============================================================
# UI
# ============================================================
with gr.Blocks(title="MCP Server Patterns Demo") as demo:
    gr.Markdown("# MCP Server Patterns — Live Demo\n"
                "Every tab shows the **MCP wire protocol (JSON-RPC 2.0)** trace so you can see exactly what flows between client and server.")

    with gr.Tabs():
        with gr.TabItem("1. Local stdio server"):
            gr.Markdown("*Custom server with all 3 primitives (tools, resources, prompts).*")
            q1 = gr.Textbox(label="Question", value="Convert 100 km to miles and give me a stock quote for INFY.")
            m1 = gr.Dropdown(MODELS, value=MODELS[0], label="Model"); b1 = gr.Button("Run", variant="primary")
            o1 = gr.Markdown(); t1 = gr.Markdown(label="MCP wire trace")
            b1.click(run_p1, [q1, m1], [o1, t1])

        with gr.TabItem("2. Remote MCP (beta)"):
            gr.Markdown("*Anthropic beta connector to a REAL remote MCP server. Set REMOTE_MCP_URL in .env.*")
            q2 = gr.Textbox(label="Question", value="What tools does this remote MCP server expose?")
            m2 = gr.Dropdown(MODELS, value=MODELS[0], label="Model"); b2 = gr.Button("Run", variant="primary")
            o2 = gr.Markdown(); t2 = gr.Markdown()
            b2.click(run_p2, [q2, m2], [o2, t2])

        with gr.TabItem("3. Multi-server orchestration"):
            gr.Markdown("*Two servers at once — Claude routes each subtask to the right one.*")
            q3 = gr.Textbox(label="Question", value="Convert 5 km to miles, then compute compound interest on 100000 at 8% for 5 years.")
            m3 = gr.Dropdown(MODELS, value=MODELS[0], label="Model"); b3 = gr.Button("Run", variant="primary")
            o3 = gr.Markdown(); t3 = gr.Markdown()
            b3.click(run_p3, [q3, m3], [o3, t3])

        with gr.TabItem("4. Resources (data pull)"):
            gr.Markdown("*Resources are read-only data (like GET) — declarative, no side effects.*")
            u4 = gr.Dropdown(["policy://kyc-summary", "customer://C-1001"], value="policy://kyc-summary", label="Resource URI")
            b4 = gr.Button("Read resource", variant="primary")
            o4 = gr.Markdown(); t4 = gr.Markdown()
            b4.click(run_p4, [u4], [o4, t4])

        with gr.TabItem("5. Prompt templates"):
            gr.Markdown("*Reusable, centrally-managed prompt templates with variable slots.*")
            tpl5 = gr.Dropdown(["structured_analysis"], value="structured_analysis", label="Template")
            topic5 = gr.Textbox(label="topic", value="the benefits of MCP servers")
            aud5 = gr.Textbox(label="audience (optional)", value="beginners")
            b5 = gr.Button("Render + run", variant="primary")
            o5 = gr.Markdown(); t5 = gr.Markdown()
            b5.click(run_p5, [tpl5, topic5, aud5], [o5, t5])

        with gr.TabItem("6. Sampling"):
            gr.Markdown("*Server-initiated LLM call: the MCP server asks the client to run a completion.*")
            txt6 = gr.Textbox(label="Text for the server to summarise", value="MCP is an open standard that lets any AI agent connect to any tool or data source through one universal protocol.")
            m6 = gr.Dropdown(MODELS, value=MODELS[0], label="Model"); b6 = gr.Button("Run sampling", variant="primary")
            o6 = gr.Markdown(); t6 = gr.Markdown()
            b6.click(run_p6, [txt6, m6], [o6, t6])

        with gr.TabItem("7. Stateless vs Stateful"):
            gr.Markdown("*Toggle the architecture. Stateless is the production-recommended (2026 spec) direction.*")
            mode7 = gr.Radio(["stateless", "stateful"], value="stateless", label="Server mode")
            q7 = gr.Textbox(label="Question", value="Set the current customer to C-1001, then tell me who the current customer is.")
            m7 = gr.Dropdown(MODELS, value=MODELS[0], label="Model"); b7 = gr.Button("Run", variant="primary")
            o7 = gr.Markdown(); t7 = gr.Markdown()
            b7.click(run_p7, [mode7, q7, m7], [o7, t7])

        with gr.TabItem("8. Banking server"):
            gr.Markdown("*Domain-specific server: account lookup, transactions, fraud score, Basel III resource, compliance prompt.*")
            q8 = gr.Textbox(label="Question", value="Look up customer C-1001, show their recent transactions, and give me their fraud risk score.")
            m8 = gr.Dropdown(MODELS, value=MODELS[0], label="Model"); b8 = gr.Button("Run", variant="primary")
            o8 = gr.Markdown(); t8 = gr.Markdown()
            b8.click(run_p8, [q8, m8], [o8, t8])

        with gr.TabItem("Compare patterns"):
            gr.Markdown("*Run the same banking question through patterns 1, 3 and 8.*")
            qc = gr.Textbox(label="Question", value="What is customer C-1001's fraud risk score?")
            mc = gr.Dropdown(MODELS, value=MODELS[0], label="Model"); bc = gr.Button("Compare", variant="primary")
            oc = gr.Markdown()
            bc.click(run_compare, [qc, mc], [oc])

        with gr.TabItem("Server status"):
            gr.Markdown("*Live MCP server processes.*")
            bs = gr.Button("Refresh status", variant="primary"); os_ = gr.Markdown()
            bs.click(server_status, [], [os_])

if __name__ == "__main__":
    env_port = os.environ.get("GRADIO_SERVER_PORT")
    chosen_port = int(env_port) if env_port else None
    if chosen_port:
        print(f"Launching on http://127.0.0.1:{chosen_port}")
    else:
        print("Launching on http://127.0.0.1:<auto-selected-port>")
    demo.launch(server_name="127.0.0.1", server_port=chosen_port, share=False)
