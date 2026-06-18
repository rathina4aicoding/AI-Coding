"""
================================================================================
 REFLECTION & CRITIQUE  (Evaluator–Optimizer Pattern)  —  LEVEL 1: BASIC
================================================================================

WHAT THIS DEMONSTRATES
----------------------
The "Reflection" / "Evaluator–Optimizer" pattern is one of the core agentic
design patterns. The idea is simple and powerful:

    1. GENERATE  -> An LLM produces a first attempt (the "Optimizer").
    2. CRITIQUE  -> An LLM reviews that attempt and gives feedback (the
                    "Evaluator").
    3. REVISE    -> An LLM rewrites the attempt using the feedback.

Just like a human writes a draft, re-reads it, and improves it, we let the
model "reflect" on its own work. In this BASIC version we run exactly ONE
reflection cycle so every step is easy to see.

    [ TASK ] --> Generate Draft --> Critique Draft --> Revise Draft --> [ DONE ]

No tools are used. This is pure prompt-based reflection. (Later levels add a
loop with a quality gate, a router, and parallel critics.)

USE CASE
--------
"Improve a piece of writing." The user types a writing task (e.g. a customer
email, a product blurb, a LinkedIn post) and watches the model draft it,
critique itself, and produce a stronger final version.

--------------------------------------------------------------------------------
 HOW TO RUN  (in VS Code)
--------------------------------------------------------------------------------
 1. Install the two libraries:
        pip install anthropic gradio

 2. Set your Anthropic API key as an environment variable:
        macOS / Linux :  export ANTHROPIC_API_KEY="sk-ant-..."
        Windows (PowerShell):  $env:ANTHROPIC_API_KEY="sk-ant-..."

 3. Run the file:
        python reflection_basic.py

 4. Open the local URL printed in the terminal (e.g. http://127.0.0.1:7860).
================================================================================
"""

import os
import anthropic
import gradio as gr
from dotenv import load_dotenv

# ------------------------------------------------------------------------------
# 1) SET UP THE CLAUDE CLIENT
# ------------------------------------------------------------------------------
# The Anthropic SDK automatically reads your key from the ANTHROPIC_API_KEY
# environment variable, so we do not paste the key in the code.
# Also accept legacy/alternate name CLAUDE_API_KEY so users who created that
# variable in their .env won't get an immediate authentication error.

# Load variables from the .env file into the environment.
load_dotenv()

# Your key is stored as CLAUDE_API_KEY, so read it by that name and pass it
# explicitly to the client (the SDK only auto-detects ANTHROPIC_API_KEY).
api_key = os.environ.get("CLAUDE_API_KEY")
if not api_key:
    raise RuntimeError("CLAUDE_API_KEY not found. Check your .env file.")

client = anthropic.Anthropic(api_key=api_key)

#_api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
#if _api_key:
#    # Pass the key explicitly to avoid SDK lookup ambiguity.
#    client = anthropic.Anthropic(api_key=_api_key)
#else:
#    # Fall back to the SDK default lookup (which may still read ANTHROPIC_API_KEY).
#    client = anthropic.Anthropic()
#    print("Warning: ANTHROPIC_API_KEY or CLAUDE_API_KEY not set. Set one before running the demo.")

# We use one fast, low-cost model for the whole demo so a classroom can run it
# cheaply. In the Evaluator–Optimizer pattern you may use a STRONGER model for
# the critic than for the generator — try swapping EVALUATOR_MODEL to
# "claude-sonnet-4-6" to feel the difference.

GENERATOR_MODEL = "claude-haiku-4-5-20251001"   # fast & cheap
EVALUATOR_MODEL = "claude-haiku-4-5-20251001"   # could be a stronger model


def call_claude(model: str, system_prompt: str, user_prompt: str,
                max_tokens: int = 1024) -> str:
    """A tiny helper that sends one message to Claude and returns the text.

    Keeping all API logic in one place makes the three stages below short and
    readable for beginners.
    """
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,                       # the model's "role"
        messages=[{"role": "user", "content": user_prompt}],
    )
    # A response can contain multiple blocks; for plain text we read the first.
    return response.content[0].text.strip()


# ------------------------------------------------------------------------------
# 2) THE THREE STAGES OF THE REFLECTION PATTERN
# ------------------------------------------------------------------------------

def generate_draft(task: str) -> str:
    """STAGE 1 — GENERATOR (Optimizer): produce a first draft."""
    system = (
        "You are a helpful writing assistant. "
        "Write a clear, focused first draft for the user's request. "
        "Output only the draft itself, with no preamble."
    )
    return call_claude(GENERATOR_MODEL, system, task)


def critique_draft(task: str, draft: str) -> str:
    """STAGE 2 — EVALUATOR (Critic): review the draft and give feedback.

    Note: the critic is told NOT to rewrite the text. Its only job is to find
    weaknesses and suggest concrete fixes. Separating 'judging' from 'fixing'
    is the heart of the Evaluator–Optimizer pattern.
    """
    system = (
        "You are a meticulous editor. Evaluate the DRAFT against the TASK. "
        "Point out specific weaknesses (clarity, completeness, tone, accuracy, "
        "length) and give 2-4 concrete, actionable suggestions as a short "
        "bulleted list. Do NOT rewrite the draft yourself."
    )
    user = f"TASK:\n{task}\n\nDRAFT:\n{draft}"
    return call_claude(EVALUATOR_MODEL, system, user)


def revise_draft(task: str, draft: str, critique: str) -> str:
    """STAGE 3 — OPTIMIZER again: rewrite the draft using the critique."""
    system = (
        "You are a skilled writer. Rewrite the draft so it addresses every "
        "point in the critique while staying true to the original task. "
        "Output only the improved version, with no preamble."
    )
    user = (
        f"TASK:\n{task}\n\n"
        f"ORIGINAL DRAFT:\n{draft}\n\n"
        f"EDITOR'S CRITIQUE:\n{critique}"
    )
    return call_claude(GENERATOR_MODEL, system, user)


# ------------------------------------------------------------------------------
# 3) ORCHESTRATION — run the three stages in sequence (one reflection cycle)
# ------------------------------------------------------------------------------

def run_reflection(task: str):
    """Run Generate -> Critique -> Revise and return all three outputs."""
    if not task or not task.strip():
        msg = "Please enter a writing task first."
        return msg, "", ""

    try:
        draft = generate_draft(task)          # Stage 1
        critique = critique_draft(task, draft)  # Stage 2
        revised = revise_draft(task, draft, critique)  # Stage 3
        return draft, critique, revised
    except Exception as e:
        # Friendly error so beginners can debug (e.g. missing API key).
        err = f"Something went wrong: {e}\n\nDid you set ANTHROPIC_API_KEY or CLAUDE_API_KEY?"
        return err, "", ""


# ------------------------------------------------------------------------------
# 4) GRADIO USER INTERFACE
# ------------------------------------------------------------------------------
# gr.Blocks lets us arrange the inputs and the three result panels neatly.

with gr.Blocks(title="Reflection & Critique — Basic") as demo:
    gr.Markdown(
        "# Reflection & Critique — Level 1: Basic\n"
        "### Evaluator–Optimizer pattern in one cycle\n"
        "Enter a writing task. Claude will **draft** it, **critique** its own "
        "draft, then produce an **improved** version."
    )

    task_input = gr.Textbox(
        label="Your writing task",
        placeholder=(
            "e.g. Write a 3-line email apologising to a customer for a delayed "
            "loan disbursement and offering a fee waiver."
        ),
        lines=3,
    )

    run_button = gr.Button("Run Reflection", variant="primary")

    # Show the three stages side by side so the improvement is visible.
    with gr.Row():
        draft_box = gr.Textbox(label="1) Draft (Generator)", lines=10)
        critique_box = gr.Textbox(label="2) Critique (Evaluator)", lines=10)
        revised_box = gr.Textbox(label="3) Improved (Optimizer)", lines=10)

    # A few ready-made examples for the classroom.
    gr.Examples(
        examples=[
            ["Write a 3-line email apologising to a customer for a delayed "
             "loan disbursement and offering a goodwill fee waiver."],
            ["Write a LinkedIn post announcing that I just completed an "
             "Agentic AI training course. Keep it humble and under 80 words."],
            ["Write a one-paragraph product description for a no-fee savings "
             "account aimed at first-time earners."],
        ],
        inputs=task_input,
    )

    # Wire the button to the orchestration function.
    run_button.click(
        fn=run_reflection,
        inputs=task_input,
        outputs=[draft_box, critique_box, revised_box],
    )


# ------------------------------------------------------------------------------
# 5) LAUNCH THE APP
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    demo.launch()
