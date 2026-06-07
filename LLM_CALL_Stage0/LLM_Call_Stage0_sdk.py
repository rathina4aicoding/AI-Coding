"""
LLM_Call_Stage0_sdk.py
----------------------
Same minimal single-call demo as LLM_Call_Stage0.py, but using the
official `anthropic` Python SDK instead of raw `requests`.

This is the recommended way - the SDK handles the endpoint URL,
required headers, request shape, and response parsing for you, so you
write a fraction of the code and there is no chance of getting any of
those details wrong.

Install:  pip install anthropic gradio python-dotenv
"""

from __future__ import annotations

import os
import sys

from anthropic import Anthropic, APIError
from dotenv import load_dotenv

import gradio as gr

load_dotenv(override=False)

API_KEY = os.getenv("CLAUDE_API_KEY")
if not API_KEY:
    sys.stderr.write(
        "ERROR: CLAUDE_API_KEY not found. Create a .env file containing:\n"
        "  CLAUDE_API_KEY=sk-ant-...\n"
    )
    sys.exit(1)

# Valid model IDs: claude-haiku-4-5, claude-sonnet-4-6,
#                  claude-opus-4-6, claude-opus-4-7
MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")

client = Anthropic(api_key=API_KEY)


def call_claude_single(user_prompt: str) -> str:
    """One single-turn call to Claude. Returns the reply text or an error."""
    if not user_prompt or not user_prompt.strip():
        return "Please enter a prompt first."

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=512,
            temperature=0.0,
            system="You are a helpful assistant. Keep answers concise and clear.",
            messages=[{"role": "user", "content": user_prompt}],
        )
    except APIError as exc:
        return f"API error: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"Unexpected error: {exc}"

    # The SDK gives us typed content blocks; concatenate the text ones.
    return "".join(
        block.text for block in message.content if block.type == "text"
    ).strip()


def build_ui() -> gr.Blocks:
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
    build_ui().launch()
