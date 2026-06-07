"""
LLM_Call_Stage0.py
------------------
Minimal example showing a single (non-conversational) Claude model call
with a simple Gradio UI. Reads `CLAUDE_API_KEY` from the environment
(or from a `.env` file when using python-dotenv).

Notes:
- No memory, no session state, not multi-turn - just one prompt -> one reply.
- Keep your API key secret. Do NOT commit `.env` with real keys to source control.
"""

from __future__ import annotations

import os
import json
import requests
from dotenv import load_dotenv

import gradio as gr

# Load .env if present
load_dotenv(override=False)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_KEY = os.getenv("CLAUDE_API_KEY")

# CORRECT Anthropic Messages API endpoint.
# (The previous /v1/chat/completions path is OpenAI's, not Anthropic's.)
API_URL = "https://api.anthropic.com/v1/messages"

# Anthropic requires this version header.
ANTHROPIC_VERSION = "2023-06-01"

# Use the canonical API model ID, NOT the display name.
# Display names like "Haiku 4.5" / "Sonnet 4.6" / "Opus 4.7" do not work.
# Valid IDs: claude-haiku-4-5, claude-sonnet-4-6, claude-opus-4-6, claude-opus-4-7
MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")


def call_claude_single(user_prompt: str) -> str:
    """Call Claude single-turn with a short system message + user prompt.

    Returns the assistant text or an error message.
    """
    if not API_KEY:
        return ("Error: CLAUDE_API_KEY not found in environment. "
                "Set it in your .env file or environment variables.")

    if not user_prompt or not user_prompt.strip():
        return "Please enter a prompt first."

    # Small system instruction to shape the reply.
    system_instruction = "You are a helpful assistant. Keep answers concise and clear." \
    "If you do not know the answer, please do not hallucinate - just say you don't know." \
    "if any hatred or sexual harassment is there in the prompt, please do not answer and say that you are not able to answer such prompts."

    # Anthropic Messages API shape:
    #   - `system` is a TOP-LEVEL field, NOT a message with role=system.
    #   - `messages` only contains user/assistant turns.
    #   - The token cap is `max_tokens`, not `max_tokens_to_sample`.
    payload = {
        "model": MODEL,
        "system": system_instruction,
        "messages": [
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 512,
        "temperature": 0.0,
    }

    # Anthropic requires the version header in addition to the API key.
    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=30)
    except requests.exceptions.RequestException as exc:
        return f"Request error: {exc}"

    if resp.status_code >= 400:
        return f"API error {resp.status_code}: {resp.text}"

    try:
        data = resp.json()
    except ValueError:
        return f"Failed to decode JSON response: {resp.text}"

    # The Messages API response shape is fixed:
    #   {
    #     "id": "...",
    #     "type": "message",
    #     "role": "assistant",
    #     "content": [{"type": "text", "text": "..."}],
    #     "model": "...",
    #     "stop_reason": "end_turn",
    #     "usage": {...}
    #   }
    # We concatenate all text blocks (there is usually just one).
    content_blocks = data.get("content", [])
    text_parts = [
        block.get("text", "")
        for block in content_blocks
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    text = "".join(text_parts).strip()

    if not text:
        return f"No assistant text found in response. Full response:\n{json.dumps(data, indent=2)}"
    return text


def build_ui() -> gr.Blocks:
    """Construct a small Gradio UI for single-turn Claude calls."""
    with gr.Blocks(title="Claude single-call demo (Stage 0)") as demo:
        gr.Markdown(
            "# Claude single-call demo\n"
            "Enter a prompt and click `Run` to get a single reply from Claude.\n"
            "(This demo does not keep memory or a conversation history.)\n\n"
            f"_Model: `{MODEL}`_"
        )

        with gr.Row():
            with gr.Column(scale=3):
                user_input = gr.Textbox(
                    label="Prompt",
                    placeholder="Ask Claude something...",
                    lines=6,
                )
                run_btn = gr.Button("Run", variant="primary")
            with gr.Column(scale=2):
                output = gr.Textbox(label="Claude reply", lines=12, interactive=False)

        run_btn.click(fn=call_claude_single, inputs=user_input, outputs=output)

    return demo


if __name__ == "__main__":
    demo = build_ui()
    demo.launch()
