# MCP Server Patterns Demo

## START HERE — 3 steps to run in VS Code

1. **Open this folder in VS Code** (File > Open Folder).
2. **Open the terminal** (Ctrl+`) and run:
   ```bash
   python -m venv .venv
   # Windows:  .venv\Scripts\activate
   # Mac/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Add your API key**: open the `.env` file and replace `sk-ant-api03-REPLACE-ME`
   with your real Anthropic key, then run:
   ```bash
   python app.py
   ```
   Open the URL it prints (http://localhost:7860) in your browser.

> Press **F5** in VS Code to run with the debugger instead (config is included).

---

A complete, runnable Python project demonstrating **every major MCP Server
design pattern** — published (remote) and custom-built — wired into one Gradio
UI that shows the full **JSON-RPC 2.0 wire protocol** for each pattern.

Built for a Gen AI & LLM Engineering workshop. Content current as of June 2026.

---

## MCP architecture (ASCII)

```
   ┌─────────────┐   JSON-RPC 2.0      ┌──────────────────┐
   │   Claude    │   over stdio /      │   MCP SERVER(s)   │
   │  (the LLM)  │   Streamable HTTP   │  tools            │
   │             │ ◄─────────────────► │  resources        │
   │  agent.py   │   initialize        │  prompts          │
   │  ReAct loop │   tools/list        │  (sampling)       │
   └─────┬───────┘   tools/call        └──────────────────┘
         │           resources/read
         │           prompts/get
   ┌─────▼───────┐
   │  Gradio UI  │   shows every message in the trace panel
   └─────────────┘
```

MCP has **three primitives**: **tools** (imperative actions, like POST),
**resources** (read-only data, like GET), and **prompts** (reusable templates).

---

## Patterns → tabs → primitives

| Tab | Pattern | MCP primitives | Server |
|-----|---------|----------------|--------|
| 1 | Local stdio server (custom) | tools, resources, prompts | general_server.py |
| 2 | Remote MCP via Anthropic connector (beta) | server-side discovery + call | (remote URL) |
| 3 | Multi-server orchestration (fan-out) | tools across 2 servers | general + math |
| 4 | Resources (document retrieval) | resources/list, resources/read | general_server.py |
| 5 | Prompt templates | prompts/list, prompts/get | general_server.py |
| 6 | Sampling (server-initiated LLM call) | sampling/createMessage | agent.py (simulated) |
| 7 | Stateless vs Stateful | tools + session contrast | stateful_server.py |
| 8 | Banking / FS domain server | tools, resources, prompts + SQLite | banking_server.py |

Plus a **Compare** tab (patterns 1/3/8 on one question) and a **Server Status**
tab (live PID, uptime, primitive counts).

---

## Project structure

```
mcp_demo/
├── app.py                      # Gradio UI — entry point
├── agent.py                    # ReAct loop, remote connector, sampling
├── mcp_client.py               # stdio MCP client + wire-trace recorder
├── db_seed.py                  # seeds banking.db (SQLite)
├── mcp_servers/
│   ├── _mcp_base.py            # minimal MCP server framework (JSON-RPC 2.0)
│   ├── general_server.py       # Pattern 1/4/5 — all 3 primitives
│   ├── math_server.py          # Pattern 3 — second server for fan-out
│   ├── banking_server.py       # Pattern 8 — domain server + SQLite
│   └── stateful_server.py      # Pattern 7 — stateless/stateful toggle
├── requirements.txt
├── .env.example
└── README.md
```

> **Note on the SDK:** the servers here implement the MCP wire protocol directly
> (zero extra dependencies) so the project runs anywhere and every JSON-RPC
> message is visible. In production, use the official `mcp` / FastMCP SDK —
> `@mcp.tool()`, `@mcp.resource()`, `@mcp.prompt()` — the message shapes are
> identical. Uncomment `mcp>=1.27.0` in requirements.txt to migrate.

---

## Setup & run

```bash
cd mcp_demo
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add your ANTHROPIC_API_KEY
python app.py                 # open http://localhost:7860
```

Pattern 2 (remote MCP) is optional — set `REMOTE_MCP_URL` in `.env` to point at
a live public MCP server. Without it, all 7 other patterns run fully locally.

---

## Why MCP is the future of agentic tool connectivity

Before MCP, every AI agent needed bespoke code to talk to every tool — an N×M
integration explosion. MCP collapses that to N+M: a tool exposes itself once as
an MCP server, and any MCP-capable agent can use it immediately. Since Anthropic
open-sourced it (Nov 2024) and donated it to the Linux Foundation (Dec 2025),
MCP has become the de-facto standard adopted by OpenAI, Google and Microsoft,
with 10,000+ public servers and ~97M SDK downloads a month. The 2026 spec push
toward a stateless protocol core means MCP servers now scale like ordinary web
services — which is exactly why it is becoming the universal connector layer for
agentic AI.
