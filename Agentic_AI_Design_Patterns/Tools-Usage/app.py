"""
app.py  —  Gradio UI for the Claude Tool Use Demo
=================================================
Run:  python app.py
      (or:  ANTHROPIC_API_KEY=sk-... python app.py)
"""

import os, json, textwrap
from dotenv import load_dotenv
load_dotenv()

import gradio as gr
from agent import run_agent, CUSTOM_TOOL_SCHEMAS, SERVER_TOOL_SCHEMAS, ALL_TOOL_NAMES

# ─────────────────────────────────────────────────────────────
# Available Claude models
# ─────────────────────────────────────────────────────────────
MODELS = [
    "claude-sonnet-4-6",   # Best for everyday agent tasks (default)
    "claude-opus-4-8",     # Most capable, use for complex reasoning
    "claude-haiku-4-5",    # Fastest, lowest cost, simple tasks
]

TOOL_LABELS = {
    "get_weather":        "🌦 Weather (Open-Meteo API)",
    "get_fx_rate":        "💱 FX Rates (Frankfurter/ECB)",
    "calculate":          "🔢 Calculator (local function)",
    "date_info":          "📅 Date / Time (local function)",
    "query_database":     "🗄 Database (SQLite — customers/orders)",
    "mcp_unit_converter": "📐 Unit Converter (local MCP server)",
    "mcp_stock_quote":    "📈 Stock Quote (local MCP server — mock)",
    "web_search":         "🔍 Web Search (Anthropic server-side)",
    "web_fetch":          "🌐 Web Fetch (Anthropic server-side)",
}

EXAMPLE_PROMPTS = [
    "What is the weather in Chennai and Mumbai right now?",
    "Convert 1 USD to INR and also tell me today's date.",
    "Calculate compound interest: principal 100000, rate 8.5%, 5 years.",
    "Show me all premium-segment customers in the database.",
    "What are the pending orders in our system?",
    "Convert 100 km to miles using the MCP unit converter.",
    "Get a stock quote for INFY and TCS from the MCP server.",
    "Search the web for the latest RBI repo rate decision.",
    "What is the current weather in London and the USD to GBP rate?",
]

# ─────────────────────────────────────────────────────────────
# Format helpers
# ─────────────────────────────────────────────────────────────

def fmt_tool_calls(tool_calls: list) -> str:
    if not tool_calls:
        return "_No tools were called for this turn._"
    lines = []
    for i, tc in enumerate(tool_calls, 1):
        args_str = json.dumps(tc["args"], indent=2)
        try:
            result_obj = json.loads(tc["result"])
            result_str = json.dumps(result_obj, indent=2)
        except Exception:
            result_str = str(tc["result"])
        lines.append(
            f"**Call {i}: `{tc['tool']}`** ({tc['elapsed_s']}s)\n"
            f"```json\n{args_str}\n```\n"
            f"**Result:**\n```json\n{result_str}\n```\n"
        )
    return "\n---\n".join(lines)

def fmt_usage(usage: dict, cost: float) -> str:
    if not usage:
        return ""
    return (f"**Tokens** — Input: {usage.get('input_tokens',0):,} | "
            f"Output: {usage.get('output_tokens',0):,} | "
            f"**Est. cost: ~${cost:.5f}**")

# ─────────────────────────────────────────────────────────────
# Main chat handler
# ─────────────────────────────────────────────────────────────

def chat(user_msg: str, history: list, model: str,
         enabled_tools: list, use_server_tools: bool):
    """
    Called by Gradio on each user turn.
    Converts Gradio history format → Anthropic messages format,
    runs the agentic loop, and returns updated state.
    """
    if not user_msg.strip():
        yield history, "", "", ""
        return

    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("CLAUDE_API_KEY"):
        err = "⚠️  ANTHROPIC_API_KEY or CLAUDE_API_KEY not set. Add it to your .env file and restart."
        # For Gradio 6.0+ Chatbot: use new message format
        new_msg = {"role": "user", "content": user_msg}
        err_msg = {"role": "assistant", "content": err}
        yield history + [new_msg, err_msg], "", "", ""
        return

    # Convert Gradio history to Anthropic format (internal use only)
    # History can be in tuple format or new message format
    anthro_history = []
    for item in history:
        if isinstance(item, dict):
            # New message format - extract only role and content
            if "role" in item and "content" in item:
                anthro_history.append({"role": item["role"], "content": item["content"]})
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            # Old tuple format - convert it
            u, a = item
            if u: anthro_history.append({"role":"user","content":u})
            if a: anthro_history.append({"role":"assistant","content":a})

    # Show "thinking…" immediately (Gradio 6.0+ format)
    thinking_msg = {"role": "assistant", "content": "⏳ Thinking…"}
    user_msg_obj = {"role": "user", "content": user_msg}
    yield history + [user_msg_obj, thinking_msg], "Running agent loop…", "", ""

    result = run_agent(
        user_message=user_msg,
        model=model,
        enabled_tools=enabled_tools,
        use_server_tools=use_server_tools,
        history=anthro_history,
    )

    # Build final history with new message format
    answer_msg = {"role": "assistant", "content": result["answer"] or "_(no text response)_"}
    new_history = history + [user_msg_obj, answer_msg]
    tool_md     = fmt_tool_calls(result["tool_calls"])
    usage_md    = fmt_usage(result["usage"], result["cost_usd"])
    status      = f"✅ Done | {len(result['tool_calls'])} tool call(s) | {usage_md}"

    yield new_history, status, tool_md, usage_md

# ─────────────────────────────────────────────────────────────
# Gradio UI
# ─────────────────────────────────────────────────────────────

with gr.Blocks(
    title="Claude Tool Use Demo",
) as demo:

    # ── Header ──────────────────────────────────────────────
    gr.Markdown("""
# 🤖 Claude Agentic Tool Use — Live Demo
**Gen AI & LLM Engineering Workshop**  
*Demonstrates every major tool-calling modality: External API · Local Function · Database · Local MCP Server · Anthropic Server-Side Tools*

> 💡 Ask about weather, FX rates, database records, unit conversions, stock quotes, or any live web question.
""")

    with gr.Row():
        # ── Left panel: chat ─────────────────────────────────
        with gr.Column(scale=3):
            chatbot = gr.Chatbot(
                label="Chat",
                height=480,
            )
            with gr.Row():
                msg_box = gr.Textbox(
                    placeholder="Ask something… e.g. 'What's the weather in Delhi?'",
                    label="Your message",
                    scale=5,
                    lines=2,
                )
                send_btn = gr.Button("Send ▶", variant="primary", scale=1)

            with gr.Accordion("💡 Example prompts", open=False):
                for ex in EXAMPLE_PROMPTS:
                    gr.Button(ex, size="sm").click(
                        fn=lambda e=ex: e, outputs=msg_box
                    )

            clear_btn = gr.Button("🗑 Clear conversation", size="sm")
            status_box = gr.Textbox(label="Status", interactive=False, lines=1)

        # ── Right panel: controls + transparency ─────────────
        with gr.Column(scale=2):
            gr.Markdown("### ⚙️ Model & Tools")
            model_dd = gr.Dropdown(
                choices=MODELS, value=MODELS[0], label="Claude model"
            )

            gr.Markdown("**Enable / disable tools:**")
            tool_checkboxes = gr.CheckboxGroup(
                choices=[(TOOL_LABELS[n], n) for n in ALL_TOOL_NAMES],
                value=ALL_TOOL_NAMES,   # all enabled by default
                label="Active tools",
            )
            server_toggle = gr.Checkbox(
                value=True, label="Include Anthropic server-side tools (web_search / web_fetch)"
            )

            gr.Markdown("---")
            gr.Markdown("### 🔍 Transparency — Tool Calls This Turn")
            tool_panel = gr.Markdown(
                value="_Tool calls will appear here after each turn._",
                label="Tool call log",
            )
            usage_panel = gr.Markdown(value="", label="Token usage")

    # ── Tool legend (educator reference) ─────────────────────
    with gr.Accordion("📚 Tool legend — what each tool does and how it connects", open=False):
        gr.Markdown("""
| Tool | Type | How it works |
|------|------|--------------|
| 🌦 **get_weather** | External API | Calls Open-Meteo REST API (free, real-time). Claude → tool_use → your code → HTTP GET → result |
| 💱 **get_fx_rate** | External API | Calls Frankfurter/ECB API (free). Same loop as above |
| 🔢 **calculate** | Local function | Pure Python — no network. Safest, fastest tool type |
| 📅 **date_info** | Local function | Pure Python datetime — no network |
| 🗄 **query_database** | DB retrieval | Claude generates filter params → parameterised SQLite query → JSON rows |
| 📐 **mcp_unit_converter** | Local MCP server | stdio JSON-RPC to local_mcp_server.py subprocess |
| 📈 **mcp_stock_quote** | Local MCP server | Same MCP server — mock data, real wiring |
| 🔍 **web_search** | Anthropic server-side | Anthropic runs the search — you only declare the tool |
| 🌐 **web_fetch** | Anthropic server-side | Anthropic fetches the page — no HTTP code on your side |

**Loop:** `User → Claude (tool_use block) → Your code / Anthropic infra → tool_result → Claude (continues) → Final Answer`
""")

    # ── Event wiring ─────────────────────────────────────────
    submit_kwargs = dict(
        fn=chat,
        inputs=[msg_box, chatbot, model_dd, tool_checkboxes, server_toggle],
        outputs=[chatbot, status_box, tool_panel, usage_panel],
    )
    send_btn.click(**submit_kwargs).then(lambda: "", outputs=msg_box)
    msg_box.submit(**submit_kwargs).then(lambda: "", outputs=msg_box)
    clear_btn.click(lambda: ([], "", "_Tool calls will appear here after each turn._", ""),
                    outputs=[chatbot, status_box, tool_panel, usage_panel])

def find_open_port(start_port: int = 7860, end_port: int = 7870) -> int:
    for port in range(start_port, end_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    raise OSError(f"Cannot find an empty port in range: {start_port}-{end_port}.")


if __name__ == "__main__":
    # Use environment variable if set, otherwise let Gradio find an open port
    env_port = os.environ.get("GRADIO_SERVER_PORT")
    chosen_port = int(env_port) if env_port else None
    
    demo.launch(
        server_name="127.0.0.1",
        server_port=chosen_port,
        share=False,
        theme=gr.themes.Soft(primary_hue="teal", neutral_hue="slate"),
    )
