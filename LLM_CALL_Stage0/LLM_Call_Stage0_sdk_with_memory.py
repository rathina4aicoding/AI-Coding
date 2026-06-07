"""
LLM_Call_Stage0_sdk_with_memory.py
----------------------------------
Stage 0 (single Claude call) -> Stage 0+ (multi-turn chat with memory).

Same minimal style as the original SDK version, but now the assistant
keeps conversation state between turns AND demonstrates two of the most
popular memory strategies side-by-side so learners can compare them:

  1. SLIDING WINDOW (a.k.a. "buffer memory")
     ---------------------------------------
     Keep the last N user/assistant turns verbatim. When the buffer
     grows past N, drop the oldest turn(s). Simple, cheap, and works
     well for short interactions, but the LLM forgets anything that
     scrolled past the window.

  2. BUFFER + RUNNING SUMMARY (a.k.a. "summary buffer memory")
     ---------------------------------------------------------
     Keep the last N turns verbatim AND a running natural-language
     summary of everything that scrolled out of the window. The summary
     itself is produced by Claude on each overflow. This costs an extra
     LLM call when the window rolls but preserves the gist of the
     entire conversation indefinitely.

Both strategies are implemented as small classes that share a common
interface, so swapping between them at runtime is just picking a
dropdown value in the Gradio UI.

Install:  pip install anthropic gradio python-dotenv
Run:      python LLM_Call_Stage0_sdk_with_memory.py
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Literal

import gradio as gr
from anthropic import Anthropic, APIError
from dotenv import load_dotenv

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

# Valid IDs: claude-haiku-4-5, claude-sonnet-4-6, claude-opus-4-6, claude-opus-4-7
MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")

client = Anthropic(api_key=API_KEY)

# Persona shared by both memory strategies.
SYSTEM_PROMPT = (
    "You are a friendly, concise assistant. Keep replies short and clear. "
    "When the user refers to earlier parts of the conversation, use the "
    "context provided to you and answer naturally - don't say 'according "
    "to my memory' or similar; just answer."
)

# System prompt used ONLY for the summarizer call in strategy #2.
SUMMARIZER_SYSTEM = (
    "You are a precise conversation summarizer. Given an existing running "
    "summary and a few new turns, produce an updated summary that captures "
    "every concrete fact, name, number, decision, and unresolved question "
    "from the inputs. Write in third person ('The user said...', 'The "
    "assistant replied...'). Stay under 6 short sentences. Do NOT add "
    "information that was not in the inputs. Respond with the updated "
    "summary as plain text only - no preamble, no headings, no JSON."
)


# ---------------------------------------------------------------------------
# Memory strategy #1: Sliding window (buffer)
# ---------------------------------------------------------------------------
@dataclass
class SlidingWindowMemory:
    """
    Keep the last `max_turns` user/assistant turn-pairs verbatim. A
    "turn pair" = one user message followed by one assistant reply, so
    `max_turns=4` means we keep at most 8 messages in the buffer.

    No LLM is called by the memory itself; we just trim the list.
    """

    max_turns: int = 4
    messages: list[dict] = field(default_factory=list)

    def build_messages_for_call(self, user_message: str) -> list[dict]:
        """Return the full `messages` array to send to client.messages.create."""
        return self.messages + [{"role": "user", "content": user_message}]

    def record_turn(self, user_message: str, assistant_text: str) -> None:
        """Append the new turn and trim the buffer if it overflows."""
        self.messages.append({"role": "user", "content": user_message})
        self.messages.append({"role": "assistant", "content": assistant_text})
        self._trim()

    def _trim(self) -> None:
        # Each "turn" is 2 messages (user + assistant).
        max_messages = self.max_turns * 2
        if len(self.messages) > max_messages:
            # Drop the oldest pairs from the front.
            overflow = len(self.messages) - max_messages
            self.messages = self.messages[overflow:]

    def reset(self) -> None:
        self.messages.clear()

    def inspect(self) -> str:
        """Return a Markdown debug view of the current memory state."""
        if not self.messages:
            return "_Buffer is empty._"
        lines = [f"**Strategy:** Sliding window (last {self.max_turns} turns)",
                 f"**Buffered messages:** {len(self.messages)}", ""]
        for i, m in enumerate(self.messages):
            role = "🧑 user" if m["role"] == "user" else "🤖 assistant"
            content = m["content"].replace("\n", " ")
            if len(content) > 200:
                content = content[:200] + "..."
            lines.append(f"{i + 1}. **{role}**: {content}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Memory strategy #2: Buffer + running summary
# ---------------------------------------------------------------------------
@dataclass
class BufferSummaryMemory:
    """
    Keep the last `max_turns` turn-pairs verbatim AND a running summary
    of everything that scrolled out of the window. When the buffer
    overflows, the oldest turn-pair is rolled into the summary by a
    short Claude call against SUMMARIZER_SYSTEM.

    The summary is injected at the top of every outgoing request as a
    [PRIOR CONVERSATION SUMMARY] block prepended to the user message so
    Claude treats it as background context.
    """

    max_turns: int = 4
    messages: list[dict] = field(default_factory=list)
    summary: str = ""

    def build_messages_for_call(self, user_message: str) -> list[dict]:
        # If we have a running summary, prepend it to the new user msg
        # so Claude has the older context without the summary itself
        # becoming part of the buffered history.
        if self.summary:
            wrapped = (
                f"[PRIOR CONVERSATION SUMMARY]\n{self.summary}\n\n"
                f"[CURRENT USER MESSAGE]\n{user_message}"
            )
        else:
            wrapped = user_message
        return self.messages + [{"role": "user", "content": wrapped}]

    def record_turn(self, user_message: str, assistant_text: str) -> None:
        # We store the CLEAN user message in the buffer (without the
        # [PRIOR SUMMARY] prefix) so the buffer stays clean for future
        # summarization passes.
        self.messages.append({"role": "user", "content": user_message})
        self.messages.append({"role": "assistant", "content": assistant_text})
        self._maybe_summarize_oldest()

    def _maybe_summarize_oldest(self) -> None:
        """If the buffer overflows, roll the oldest turn-pair into the summary."""
        max_messages = self.max_turns * 2
        while len(self.messages) > max_messages:
            # Pop the oldest pair (user + assistant).
            oldest_user = self.messages.pop(0)
            oldest_assistant = (
                self.messages.pop(0) if self.messages else
                {"role": "assistant", "content": ""}
            )
            turn_text = (
                f"USER: {oldest_user['content']}\n"
                f"ASSISTANT: {oldest_assistant['content']}"
            )
            self.summary = _summarize(self.summary, turn_text)

    def reset(self) -> None:
        self.messages.clear()
        self.summary = ""

    def inspect(self) -> str:
        lines = [
            f"**Strategy:** Buffer + running summary (last "
            f"{self.max_turns} turns kept verbatim)",
            "",
            "**Running summary:**",
            f"> {self.summary}" if self.summary else "_(empty - kicks in once "
            f"the buffer holds more than {self.max_turns} turns)_",
            "",
            f"**Buffered messages:** {len(self.messages)}",
        ]
        for i, m in enumerate(self.messages):
            role = "🧑 user" if m["role"] == "user" else "🤖 assistant"
            content = m["content"].replace("\n", " ")
            if len(content) > 200:
                content = content[:200] + "..."
            lines.append(f"{i + 1}. **{role}**: {content}")
        return "\n".join(lines)


def _summarize(prior_summary: str, new_turn_text: str) -> str:
    """Roll an old turn into the running summary via a small Claude call."""
    prompt = (
        f"Existing running summary (may be empty):\n"
        f'"""\n{prior_summary}\n"""\n\n'
        f"New turn(s) to fold in:\n"
        f'"""\n{new_turn_text}\n"""\n\n'
        f"Produce the updated running summary now."
    )
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=512,
            temperature=0.0,
            system=SUMMARIZER_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            b.text for b in resp.content if b.type == "text"
        ).strip()
    except APIError as exc:
        # If the summarizer call fails we keep the prior summary intact
        # rather than losing it - graceful degradation.
        return prior_summary or f"[summarizer error: {exc}]"


# ---------------------------------------------------------------------------
# Chat function (works with either memory class via duck typing)
# ---------------------------------------------------------------------------
StrategyName = Literal["sliding_window", "buffer_summary"]


def _get_or_init_memory(
    state: dict,
    strategy: StrategyName,
    max_turns: int,
) -> SlidingWindowMemory | BufferSummaryMemory:
    """
    Return the memory object for the active strategy from `state`. If
    the strategy or max_turns changed since last call, build a fresh
    memory of the right type (so switching strategies in the UI feels
    intentional, not magical).
    """
    current = state.get("memory")
    current_strategy = state.get("strategy")
    current_max_turns = state.get("max_turns")

    needs_rebuild = (
        current is None
        or current_strategy != strategy
        or current_max_turns != max_turns
    )
    if needs_rebuild:
        if strategy == "sliding_window":
            current = SlidingWindowMemory(max_turns=max_turns)
        else:
            current = BufferSummaryMemory(max_turns=max_turns)
        state["memory"] = current
        state["strategy"] = strategy
        state["max_turns"] = max_turns
    return current


def chat_once(
    user_message: str,
    chat_history: list[dict],
    state: dict,
    strategy_label: str,
    max_turns: int,
) -> tuple[list[dict], dict, str, str]:
    """
    Gradio callback. Returns:
      (updated_chat_history, updated_state, memory_inspector_md, status_md)
    """
    if not user_message or not user_message.strip():
        memory = state.get("memory")
        inspector = memory.inspect() if memory else "_No memory yet._"
        return chat_history, state, inspector, "❗ Please type a message."

    # Map the dropdown label back to the strategy name.
    strategy: StrategyName = (
        "sliding_window"
        if strategy_label.startswith("1.")
        else "buffer_summary"
    )

    memory = _get_or_init_memory(state, strategy, int(max_turns))

    # Build the request and call Claude.
    messages = memory.build_messages_for_call(user_message)
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=512,
            temperature=0.3,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
    except APIError as exc:
        return (
            chat_history,
            state,
            memory.inspect(),
            f"❌ API error: {exc}",
        )
    except Exception as exc:  # noqa: BLE001
        return (
            chat_history,
            state,
            memory.inspect(),
            f"❌ Unexpected error: {exc}",
        )

    assistant_text = "".join(
        b.text for b in response.content if b.type == "text"
    ).strip()

    # Record into memory.
    memory.record_turn(user_message, assistant_text)

    # Update the visible chat history.
    new_chat = chat_history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": assistant_text},
    ]

    status = (
        f"✅ Replied. Strategy: **{strategy}**, "
        f"max_turns={max_turns}, "
        f"buffered messages={len(memory.messages)}"
    )
    return new_chat, state, memory.inspect(), status


def reset_all(state: dict) -> tuple[list[dict], dict, str, str]:
    """Wipe chat + memory."""
    memory = state.get("memory")
    if memory is not None:
        memory.reset()
    return [], state, "_Buffer is empty._", "🔄 Reset complete."


# ---------------------------------------------------------------------------
# Gradio UI
# ---------------------------------------------------------------------------
STRATEGY_CHOICES = [
    "1. Sliding window (buffer)",
    "2. Buffer + running summary",
]

DEFAULT_MAX_TURNS = 3


EXAMPLE_TURNS = [
    "Hi! I'm Priya and I work in the data platform team.",
    "I'm prototyping a Q&A bot in Python with Gradio.",
    "We use Postgres for our metadata, not MySQL.",
    "Remind me - which database did I say we use?",
    "Could you also recall my name and team?",
]


def build_ui() -> gr.Blocks:
    with gr.Blocks(
        title="Claude chat with memory (Stage 0+)",
        theme=gr.themes.Soft(primary_hue="sky", neutral_hue="slate"),
    ) as demo:
        gr.Markdown(
            "# 💬 Claude chat with memory (Stage 0+)\n"
            "Single-turn Stage 0, upgraded with conversation state and two "
            "popular memory strategies you can swap between live:\n\n"
            "1. **Sliding window** - keep last N turns verbatim, drop the rest.\n"
            "2. **Buffer + running summary** - keep last N turns verbatim, "
            "and roll older turns into a Claude-generated summary so nothing "
            "is fully forgotten.\n\n"
            f"_Model: `{MODEL}`_"
        )

        # Per-session state (each browser tab gets its own).
        state = gr.State(value={})

        with gr.Row():
            with gr.Column(scale=2):
                strategy_dd = gr.Dropdown(
                    label="Memory strategy",
                    choices=STRATEGY_CHOICES,
                    value=STRATEGY_CHOICES[0],
                    info="Switch and watch the inspector below change.",
                )
                max_turns_slider = gr.Slider(
                    label="Max turns kept verbatim (a 'turn' = user + assistant)",
                    minimum=1, maximum=10, step=1, value=DEFAULT_MAX_TURNS,
                    info="Smaller -> more aggressive forgetting / summarizing.",
                )
                reset_btn = gr.Button("🔄 Reset chat + memory", size="sm")
                gr.Markdown(
                    "**Try this demo flow** to see the difference:\n"
                    "1. Send the example messages 1-4 in order.\n"
                    "2. Look at the Memory inspector after each turn.\n"
                    "3. Then send message 5. Compare the answer under each "
                    "strategy after the buffer has overflowed."
                )

            with gr.Column(scale=3):
                chatbot = gr.Chatbot(
                    height=420,
                    show_label=False,
                    avatar_images=(None, "🤖"),
                )
                with gr.Row():
                    user_box = gr.Textbox(
                        placeholder="Type a message and press Enter...",
                        scale=5,
                        autofocus=True,
                        show_label=False,
                    )
                    send_btn = gr.Button("Send", variant="primary", scale=1)
                gr.Examples(
                    examples=EXAMPLE_TURNS,
                    inputs=user_box,
                    label="Click an example to fill the textbox",
                )
                status_md = gr.Markdown(value="_Ready._")

        gr.Markdown("---\n## 🔍 Memory inspector")
        gr.Markdown(
            "_This is the actual state passed to Claude on the next turn. "
            "For sliding window you see only the buffer; for buffer+summary "
            "you see both the running summary and the buffered tail._"
        )
        inspector_md = gr.Markdown(value="_Buffer is empty._")

        # ---- Wiring ----
        send_event = send_btn.click(
            fn=chat_once,
            inputs=[user_box, chatbot, state, strategy_dd, max_turns_slider],
            outputs=[chatbot, state, inspector_md, status_md],
        )
        send_event.then(lambda: "", outputs=user_box)

        submit_event = user_box.submit(
            fn=chat_once,
            inputs=[user_box, chatbot, state, strategy_dd, max_turns_slider],
            outputs=[chatbot, state, inspector_md, status_md],
        )
        submit_event.then(lambda: "", outputs=user_box)

        reset_btn.click(
            fn=reset_all,
            inputs=[state],
            outputs=[chatbot, state, inspector_md, status_md],
        )

        gr.Markdown(
            "---\n_Stage 0+ adds memory only. We deliberately still have no "
            "tools, no database, no retrieval - those come in Stages 2-4 "
            "of the training._"
        )

    return demo


if __name__ == "__main__":
    build_ui().launch(server_name="127.0.0.1", server_port=7860, share=False)
