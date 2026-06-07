"""
LLM_Call_Stage0_sdk_with_mcp.py
-------------------------------
Stage 0 (single Claude call) -> Stage 0 + MCP servers.

This is the same "ask Claude a question and let it call tools" pattern as
the previous Stage 0 examples, but instead of registering Python
functions directly with Claude, we connect to THREE LOCAL MCP SERVERS
over stdio:

  1. Time MCP server     - real-time date/time/timezone conversion
                           (uses timeapi.io with a zoneinfo fallback)
  2. Google Drive MCP    - list/search/read documents (mocked workspace)
  3. GitHub MCP          - search code, list/create issues, PRs (mocked)

Each server is a separate Python script (see mcp_servers/) that we
launch as a subprocess. On startup we:

  1. Spawn each server.
  2. Complete the MCP handshake on each connection.
  3. Call list_tools() to discover what each server offers.
  4. Convert each MCP tool schema into the Anthropic-API tool shape and
     register it with Claude, prefixing names by server (e.g.
     `time__get_current_time`) to avoid collisions.

When the user asks something, Claude returns `tool_use` blocks naming
those prefixed tools; we route each call back to the right server, get
the result, and feed it to Claude as a `tool_result`. Same protocol you
saw without MCP - just now the implementations live in independent
processes.

Install:  pip install anthropic gradio python-dotenv mcp requests
Run:      python LLM_Call_Stage0_sdk_with_mcp.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import gradio as gr
from anthropic import Anthropic, APIError
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
load_dotenv(override=False)

API_KEY = os.getenv("CLAUDE_API_KEY")
if not API_KEY:
    sys.stderr.write(
        "ERROR: CLAUDE_API_KEY not found. Create a .env file containing:\n"
        "  CLAUDE_API_KEY=sk-ant-...\n"
    )
    sys.exit(1)

MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")

# Safety cap on tool-use rounds per user turn.
MAX_TOOL_ITERATIONS = 6

client = Anthropic(api_key=API_KEY)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)-18s | %(message)s",
    datefmt="%H:%M:%S",
)
# Quiet noisy third-party loggers
for noisy in ("httpx", "httpcore", "anthropic", "mcp", "asyncio"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("stage0.mcp")

SYSTEM_PROMPT = (
    "You are a friendly, concise assistant with access to three MCP "
    "servers that expose real tools:\n"
    "  - Time:        date/time/timezone tools (prefix `time__`)\n"
    "  - GoogleDrive: workspace document tools (prefix `gdrive__`)\n"
    "  - GitHub:      source-control tools (prefix `github__`)\n\n"
    "When the user asks about current date/time, timezone conversions, "
    "company documents, repositories, pull requests, code, or issues, "
    "call the right tool from the right server. For unrelated questions "
    "answer directly without calling tools. After a tool returns, "
    "summarize the result for the user in plain English - do not dump "
    "raw JSON at them."
)


# ===========================================================================
# MCP server registry
# ===========================================================================
_HERE = Path(__file__).parent
_SERVERS_DIR = _HERE / "mcp_servers"


@dataclass(frozen=True)
class MCPServerConfig:
    name: str            # human-readable label, shown in UI/logs
    prefix: str          # tool-name prefix exposed to Claude
    script_path: Path    # absolute path to the server script
    emoji: str           # for activity-log pretty printing


MCP_SERVERS = [
    MCPServerConfig(
        name="Time", prefix="time", emoji="⏰",
        script_path=_SERVERS_DIR / "time_server.py",
    ),
    MCPServerConfig(
        name="GoogleDrive", prefix="gdrive", emoji="📁",
        script_path=_SERVERS_DIR / "gdrive_server.py",
    ),
    MCPServerConfig(
        name="GitHub", prefix="github", emoji="🐙",
        script_path=_SERVERS_DIR / "github_server.py",
    ),
]

# Double underscore is safe under Anthropic's tool-name pattern.
PREFIX_SEP = "__"


# ===========================================================================
# MCP client hub
# ===========================================================================
@dataclass
class _ServerConnection:
    config: MCPServerConfig
    session: ClientSession
    local_tools: dict[str, dict] = field(default_factory=dict)


class MCPHub:
    """
    Spawns the configured MCP servers, holds open ClientSessions for the
    life of the process, and exposes the unified tool list + a dispatch
    method to the agent loop.
    """

    def __init__(self) -> None:
        self._stack: AsyncExitStack | None = None
        self._connections: list[_ServerConnection] = []
        # fq_name (e.g. "time__get_current_time") -> (connection, local_name)
        self._routes: dict[str, tuple[_ServerConnection, str]] = {}
        # Cached Anthropic-shape tool list
        self._tools_for_claude: list[dict] = []

    async def start(self) -> None:
        if self._stack is not None:
            return
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        for cfg in MCP_SERVERS:
            await self._connect(cfg)
        log.info("MCP hub ready: %d servers, %d tools total",
                 len(self._connections), len(self._routes))

    async def _connect(self, cfg: MCPServerConfig) -> None:
        if not cfg.script_path.exists():
            log.error("Server script missing: %s", cfg.script_path)
            return
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(cfg.script_path)],
            env=None,
        )
        log.info("Connecting to %s server: %s", cfg.name, cfg.script_path.name)
        assert self._stack is not None
        try:
            read, write = await self._stack.enter_async_context(stdio_client(params))
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            tools = await session.list_tools()
        except Exception as exc:  # noqa: BLE001
            log.exception("Failed to connect to %s: %s", cfg.name, exc)
            return

        conn = _ServerConnection(config=cfg, session=session)
        for t in tools.tools:
            conn.local_tools[t.name] = {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.inputSchema,
            }
            fq = f"{cfg.prefix}{PREFIX_SEP}{t.name}"
            self._routes[fq] = (conn, t.name)
            self._tools_for_claude.append({
                "name": fq,
                "description": f"[{cfg.name}] {t.description or ''}".strip(),
                "input_schema": t.inputSchema,
            })
        self._connections.append(conn)
        log.info("%s: discovered %d tools (%s)",
                 cfg.name, len(conn.local_tools),
                 ", ".join(sorted(conn.local_tools)))

    async def shutdown(self) -> None:
        if self._stack is None:
            return
        try:
            await self._stack.__aexit__(None, None, None)
        finally:
            self._stack = None
            self._connections.clear()
            self._routes.clear()
            self._tools_for_claude.clear()

    @property
    def tools_for_claude(self) -> list[dict]:
        return list(self._tools_for_claude)

    def server_for(self, fq_tool_name: str) -> MCPServerConfig | None:
        hit = self._routes.get(fq_tool_name)
        return hit[0].config if hit else None

    def describe_servers(self) -> list[dict]:
        out = []
        for c in self._connections:
            out.append({
                "name": c.config.name,
                "emoji": c.config.emoji,
                "prefix": c.config.prefix,
                "tools": sorted(c.local_tools),
            })
        return out

    async def call_tool(self, fq_tool_name: str, args: dict) -> tuple[dict, bool]:
        """
        Dispatch a tool by its fully-qualified name.
        Returns (output_dict, is_error).
        """
        hit = self._routes.get(fq_tool_name)
        if hit is None:
            return {"error": f"Unknown tool {fq_tool_name!r}"}, True
        conn, local_name = hit
        try:
            result = await conn.session.call_tool(local_name, arguments=args or {})
        except Exception as exc:  # noqa: BLE001
            log.exception("Tool %s raised", fq_tool_name)
            return {"error": f"{type(exc).__name__}: {exc}"}, True
        return _coerce_mcp_result(result)


def _coerce_mcp_result(result: Any) -> tuple[dict, bool]:
    """
    FastMCP tools that return a dict wrap it as TextContent blocks
    containing the JSON-encoded payload. Unwrap that.
    Returns (output_dict, is_error).
    """
    is_error = bool(getattr(result, "isError", False))
    blocks = getattr(result, "content", None) or []
    texts: list[str] = []
    for b in blocks:
        if getattr(b, "type", None) == "text" and hasattr(b, "text"):
            texts.append(b.text)
        else:
            texts.append(str(b))
    combined = "\n".join(texts).strip()

    if combined:
        try:
            parsed = json.loads(combined)
            if isinstance(parsed, dict):
                # Tool functions that returned {"error": "..."} count as errors
                if "error" in parsed and len(parsed) <= 2:
                    is_error = True
                return parsed, is_error
            return {"result": parsed}, is_error
        except json.JSONDecodeError:
            pass
    return {"text": combined}, is_error


# Module-level singleton
hub = MCPHub()


# ===========================================================================
# The agent loop (async because the MCP SDK is async-only)
# ===========================================================================
async def _chat_with_mcp(user_message: str) -> tuple[str, list[str]]:
    """Run one turn through the tool-use loop. Returns (reply, activity_log)."""
    if not user_message or not user_message.strip():
        return "Please type a message.", []

    messages: list[dict] = [{"role": "user", "content": user_message}]
    activity: list[str] = []
    final_text_parts: list[str] = []
    tools = hub.tools_for_claude

    for iteration in range(MAX_TOOL_ITERATIONS):
        activity.append(f"_Iteration {iteration + 1}: calling Claude..._")
        try:
            response = await asyncio.to_thread(
                client.messages.create,
                model=MODEL,
                max_tokens=1024,
                temperature=0.0,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            )
        except APIError as exc:
            return f"❌ API error: {exc}", activity

        # Persist the assistant message verbatim so tool_use IDs match.
        messages.append({"role": "assistant", "content": response.content})

        tool_uses_this_round: list[dict] = []
        for block in response.content:
            if block.type == "text":
                if block.text.strip():
                    final_text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses_this_round.append(
                    {"id": block.id, "name": block.name, "input": block.input}
                )
                srv = hub.server_for(block.name)
                emoji = srv.emoji if srv else "🛠️"
                srv_name = srv.name if srv else "?"
                activity.append(
                    f"### {emoji} `{srv_name}` server: calling `{block.name}`\n"
                    f"```json\n{json.dumps(block.input, indent=2)}\n```"
                )

        if response.stop_reason != "tool_use":
            break

        # Execute every requested tool and pack the results into ONE user message.
        tool_result_blocks: list[dict] = []
        for tu in tool_uses_this_round:
            output, is_error = await hub.call_tool(tu["name"], tu["input"])
            srv = hub.server_for(tu["name"])
            emoji_icon = "❌" if is_error else "✅"
            srv_emoji = srv.emoji if srv else ""
            srv_name = srv.name if srv else "?"

            preview = json.dumps(output, indent=2, default=str)
            if len(preview) > 700:
                preview = preview[:700] + "\n  ... (truncated)"
            activity.append(
                f"### {emoji_icon} Result from {srv_emoji} `{srv_name}` :: "
                f"`{tu['name']}`\n```json\n{preview}\n```"
            )

            tool_result_blocks.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": json.dumps(output, default=str),
                **({"is_error": True} if is_error else {}),
            })

        messages.append({"role": "user", "content": tool_result_blocks})
    else:
        activity.append(
            f"_Stopped after {MAX_TOOL_ITERATIONS} iterations (safety cap)._"
        )

    reply = "".join(final_text_parts).strip() or "_(no text reply)_"
    return reply, activity


# ===========================================================================
# Gradio glue
# ===========================================================================
# We start the hub once, lazily, on the first user message. After that
# it stays open for the life of the process.
_hub_started: asyncio.Event | None = None
_start_lock: asyncio.Lock | None = None


async def _ensure_hub_started() -> None:
    global _hub_started, _start_lock
    if _hub_started is None:
        _start_lock = asyncio.Lock()
        _hub_started = asyncio.Event()
    if _hub_started.is_set():
        return
    assert _start_lock is not None
    async with _start_lock:
        if _hub_started.is_set():
            return
        await hub.start()
        _hub_started.set()


async def run_chat(user_message: str) -> tuple[str, str, str]:
    """Gradio callback. Returns (reply_md, activity_md, servers_md)."""
    await _ensure_hub_started()
    reply, activity = await _chat_with_mcp(user_message)
    activity_md = (
        "\n\n".join(activity) if activity
        else "_No tool calls were made for this question._"
    )
    return reply, activity_md, _format_servers_md()


def _format_servers_md() -> str:
    rows = hub.describe_servers()
    if not rows:
        return "_MCP hub not yet initialized._"
    lines = ["**Discovered MCP servers & their tools:**", ""]
    for r in rows:
        lines.append(
            f"{r['emoji']} **{r['name']}** (prefix `{r['prefix']}__*`)  "
        )
        lines.append("Tools: " + ", ".join(f"`{t}`" for t in r["tools"]))
        lines.append("")
    return "\n".join(lines)


EXAMPLE_PROMPTS = [
    "What time is it right now in Tokyo and London?",
    "Convert 9:00 in New York to London time.",
    "Search my Google Drive for any docs about VPN setup.",
    "Read the file about MCP adoption from Google Drive.",
    "What pull requests are open in the techmate-bot repo?",
    "Show me any open issues with the 'bug' label.",
    "Search the techmate-bot repo code for 'tool_use'.",
    "File a new GitHub issue in techmate-bot titled 'Add retry on MCP startup' with body 'Sometimes the gdrive server takes >5s to start; client should retry once.'",
    "What's the capital of Australia?",  # should NOT call any tool
]


def build_ui() -> gr.Blocks:
    with gr.Blocks(
        title="Claude with MCP Servers (Stage 0+)",
        theme=gr.themes.Soft(primary_hue="sky", neutral_hue="slate"),
    ) as demo:
        gr.Markdown(
            "# 🔌 Claude with MCP Servers (Stage 0+)\n"
            "Single-turn Stage 0, now wired up to **three local MCP servers** "
            "running as separate processes over stdio:\n\n"
            "- ⏰ **Time** — current date/time and timezone conversion "
            "(real API call to timeapi.io, with offline fallback)\n"
            "- 📁 **Google Drive** — list, search, and read workspace "
            "documents (mocked workspace, real MCP protocol)\n"
            "- 🐙 **GitHub** — search code, list/create issues, look at "
            "PRs (mocked, real MCP protocol)\n\n"
            "When you ask, Claude decides which tool to call, the request "
            "is routed to the right server, and the result flows back. "
            "On your first question the three subprocesses are launched "
            "and their tools are auto-discovered.\n\n"
            f"_Model: `{MODEL}`_"
        )

        with gr.Row():
            with gr.Column(scale=3):
                user_input = gr.Textbox(
                    label="Your question",
                    placeholder=(
                        "Try: 'What time is it in Tokyo?' or "
                        "'Search Drive for VPN setup' or "
                        "'List open PRs in techmate-bot'"
                    ),
                    lines=3,
                    autofocus=True,
                )
                with gr.Row():
                    run_btn = gr.Button("Ask", variant="primary")
                    clear_btn = gr.Button("Clear", size="sm")
                gr.Examples(
                    examples=EXAMPLE_PROMPTS,
                    inputs=user_input,
                    label="Example prompts (click to fill)",
                )
            with gr.Column(scale=4):
                reply_out = gr.Markdown(
                    label="Reply",
                    value="_Claude's reply will appear here._",
                    height=220,
                )

        gr.Markdown("---\n## 🔍 MCP activity for the latest question")
        gr.Markdown(
            "_Every tool call routed to an MCP server, and every result "
            "returned, in order. Each entry is labelled with the server "
            "that handled it._"
        )
        activity_out = gr.Markdown(
            value="_No question asked yet._",
            height=360,
        )

        with gr.Accordion("ℹ️ Connected MCP servers", open=False):
            servers_md = gr.Markdown(
                value="_The MCP hub initializes on your first question._"
            )

        # ---- Wiring ----
        run_btn.click(
            fn=run_chat,
            inputs=user_input,
            outputs=[reply_out, activity_out, servers_md],
        )
        user_input.submit(
            fn=run_chat,
            inputs=user_input,
            outputs=[reply_out, activity_out, servers_md],
        )
        clear_btn.click(
            fn=lambda: ("",
                        "_Claude's reply will appear here._",
                        "_No question asked yet._"),
            outputs=[user_input, reply_out, activity_out],
        )

        gr.Markdown(
            "---\n_Stage 0+ adds MCP-backed tooling only. Memory and "
            "multi-turn chat come in later stages of the training._"
        )

    return demo


if __name__ == "__main__":
    build_ui().launch(server_name="127.0.0.1", server_port=7860, share=False)
