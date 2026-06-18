"""
================================================================================
 REFLECTION & CRITIQUE  (Evaluator–Optimizer Pattern) — LEVEL 2: INTERMEDIATE
================================================================================

WHAT'S NEW VS. THE BASIC VERSION
--------------------------------
The Basic demo ran ONE reflection cycle (draft -> critique -> revise) and
stopped. Real agentic systems keep reflecting until the work is "good enough".

This Intermediate version adds three important ideas:

  1. A SCORING EVALUATOR  -> the critic now returns a STRUCTURED verdict
                             (a JSON object with a 1-10 score + feedback) so
                             our code can make a decision, not just print text.

  2. A QUALITY GATE (a conditional "router")  -> if the score meets the
                             threshold we STOP; otherwise we revise and loop.

  3. A REVISION BUDGET  -> a maximum number of revisions so the loop can never
                             run forever (this controls cost and latency).

The flow becomes a LOOP:

        +-----------------------------------------------+
        |                                               |
   [TASK] -> Draft -> Evaluate (score) --PASS?--> NO ---+   (revise & repeat)
                              |
                             YES  or  budget used up
                              |
                              v
                          [FINAL DRAFT]

This combines two building blocks you teach:
    * Prompt chaining (sequential): draft -> critique -> revise
    * Router (conditional):         "PASS vs REVISE" decision on the score

USE CASE (same context as Basic): "Improve a piece of writing", but now we
iterate until a quality bar is met. Great for customer comms in a bank where
tone and completeness matter.

--------------------------------------------------------------------------------
 HOW TO RUN  (in VS Code)
--------------------------------------------------------------------------------
 1. Install libraries:
        pip install anthropic gradio python-dotenv

 2. Put your key in a file named  .env  (same folder as this script):
        CLAUDE_API_KEY=sk-ant-...

 3. Run:
        python reflection_intermediate.py
================================================================================
"""

import os
import re
import json
import anthropic
import gradio as gr
from dotenv import load_dotenv

# ------------------------------------------------------------------------------
# 1) SET UP THE CLAUDE CLIENT  (reads CLAUDE_API_KEY from your .env file)
# ------------------------------------------------------------------------------
load_dotenv()
api_key = os.environ.get("CLAUDE_API_KEY")
if not api_key:
    raise RuntimeError("CLAUDE_API_KEY not found. Check your .env file.")

client = anthropic.Anthropic(api_key=api_key)

# A key teaching point of Evaluator–Optimizer: the EVALUATOR can be a different
# (often stronger) model than the GENERATOR. Here we let a fast model write and
# a sharper model judge. Try making them the same to compare behaviour.
GENERATOR_MODEL = "claude-haiku-4-5-20251001"   # fast & cheap: drafts + revisions
EVALUATOR_MODEL = "claude-sonnet-4-6"           # sharper judgement for scoring


def call_claude(model: str, system_prompt: str, user_prompt: str,
                max_tokens: int = 1024) -> str:
    """Send one message to Claude and return the plain text reply."""
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text.strip()


# ------------------------------------------------------------------------------
# 2) THE THREE STAGES
# ------------------------------------------------------------------------------

def generate_draft(task: str) -> str:
    """GENERATOR: produce the first draft."""
    system = (
        "You are a helpful writing assistant. Write a clear, focused first "
        "draft for the user's request. Output only the draft, no preamble."
    )
    return call_claude(GENERATOR_MODEL, system, task)


def evaluate_draft(task: str, draft: str) -> tuple[int, str]:
    """EVALUATOR: score the draft and return (score, feedback).

    The critic must reply with ONLY a JSON object so our code can read the
    score reliably. Forcing structured output is what turns a free-text
    critique into a decision the program can act on.
    """
    system = (
        "You are a strict quality evaluator. Score the DRAFT against the TASK "
        "on a 1-10 scale (10 = excellent and fully meets the task; consider "
        "clarity, completeness, tone, accuracy, and length constraints).\n"
        "Respond with ONLY a JSON object, no other text, in exactly this form:\n"
        '{"score": <integer 1-10>, "feedback": "<specific, actionable '
        'suggestions; or \'Looks good.\' if no changes are needed>"}'
    )
    user = f"TASK:\n{task}\n\nDRAFT:\n{draft}"
    raw = call_claude(EVALUATOR_MODEL, system, user)
    return parse_evaluation(raw)


def parse_evaluation(raw: str) -> tuple[int, str]:
    """Safely pull the score and feedback out of the evaluator's JSON reply.

    Models occasionally wrap JSON in code fences or add stray text, so we
    extract the first {...} block and parse it. If anything fails, we assume
    the draft still needs work (score 5) and pass the raw text as feedback.
    """
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            score = int(data.get("score", 5))
            feedback = str(data.get("feedback", "")).strip()
            # Clamp the score into the valid 1-10 range.
            score = max(1, min(10, score))
            return score, feedback or "(no feedback provided)"
        except Exception:
            pass
    return 5, raw  # fallback if the reply was not valid JSON


def revise_draft(task: str, draft: str, feedback: str) -> str:
    """OPTIMIZER: rewrite the draft using the evaluator's feedback."""
    system = (
        "You are a skilled writer. Rewrite the draft so it addresses every "
        "point in the feedback while staying true to the original task. "
        "Output only the improved version, no preamble."
    )
    user = (
        f"TASK:\n{task}\n\n"
        f"CURRENT DRAFT:\n{draft}\n\n"
        f"EVALUATOR FEEDBACK:\n{feedback}"
    )
    return call_claude(GENERATOR_MODEL, system, user)


# ------------------------------------------------------------------------------
# 3) THE REFLECTION LOOP  (generator: streams progress to the UI as it runs)
# ------------------------------------------------------------------------------
# Using a Python generator (yield) lets the Gradio UI update after every step,
# so the class can WATCH the score climb across iterations.

def run_reflection_loop(task: str, threshold: float, max_revisions: float):
    threshold = int(threshold)
    max_revisions = int(max_revisions)

    if not task or not task.strip():
        yield "Please enter a writing task first.", ""
        return

    log_parts: list[str] = []

    def render() -> str:
        return "\n\n".join(log_parts)

    try:
        # ----- Draft 1 (initial) -----
        draft = generate_draft(task)
        log_parts.append(f"## 📝 Draft 1 (initial)\n{draft}")
        yield render(), draft

        revisions_done = 0
        while True:
            # ----- Evaluate the current draft (the quality gate) -----
            score, feedback = evaluate_draft(task, draft)
            passed = score >= threshold
            verdict = "PASS ✅" if passed else "REVISE 🔁"
            log_parts.append(
                f"## 🔍 Evaluation of Draft {revisions_done + 1}\n"
                f"**Score: {score}/10 → {verdict}**  (threshold = {threshold})\n\n"
                f"**Feedback:** {feedback}"
            )
            yield render(), draft

            # ----- CONDITIONAL ROUTER: decide whether to stop or loop -----
            if passed:
                log_parts.append(
                    f"## 🏁 Finished — passed on attempt {revisions_done + 1}."
                )
                yield render(), draft
                return

            if revisions_done >= max_revisions:
                log_parts.append(
                    f"## 🏁 Finished — hit the revision budget "
                    f"({max_revisions}). Returning the best effort so far."
                )
                yield render(), draft
                return

            # ----- Otherwise: revise and go around the loop again -----
            revisions_done += 1
            draft = revise_draft(task, draft, feedback)
            log_parts.append(f"## ✍️ Draft {revisions_done + 1} (revised)\n{draft}")
            yield render(), draft

    except Exception as e:
        log_parts.append(f"**Something went wrong:** {e}")
        yield render(), ""


# ------------------------------------------------------------------------------
# 4) GRADIO USER INTERFACE
# ------------------------------------------------------------------------------

with gr.Blocks(title="Reflection & Critique — Intermediate") as demo:
    gr.Markdown(
        "# Reflection & Critique — Level 2: Intermediate\n"
        "### Evaluator–Optimizer with a scoring quality gate + revision loop\n"
        "Claude drafts, **scores its own work 1–10**, and keeps revising until "
        "the score clears your **threshold** or it runs out of **revisions**."
    )

    task_input = gr.Textbox(
        label="Your writing task",
        placeholder=(
            "e.g. Write a 4-line email to a customer whose KYC documents have "
            "expired, asking them to re-submit, with a clear 7-day deadline and "
            "a reassuring tone."
        ),
        lines=3,
    )

    with gr.Row():
        threshold_slider = gr.Slider(
            minimum=5, maximum=10, value=8, step=1,
            label="Quality threshold (score needed to PASS)",
        )
        revisions_slider = gr.Slider(
            minimum=1, maximum=4, value=3, step=1,
            label="Max revisions (loop budget)",
        )

    run_button = gr.Button("Run Reflection Loop", variant="primary")

    with gr.Row():
        # The log streams live as the loop runs; the final box holds the result.
        log_output = gr.Markdown(label="Reflection log")
        final_output = gr.Textbox(label="Final version", lines=18)

    gr.Examples(
        examples=[
            ["Write a 4-line email to a customer whose KYC documents have "
             "expired, asking them to re-submit, with a clear 7-day deadline "
             "and a reassuring tone.", 8, 3],
            ["Summarise the benefits of a no-fee savings account in EXACTLY "
             "two sentences for a first-time earner.", 9, 3],
            ["Write a short, honest, encouraging email telling a customer their "
             "loan application was declined and what they can do next.", 8, 3],
        ],
        inputs=[task_input, threshold_slider, revisions_slider],
    )

    run_button.click(
        fn=run_reflection_loop,
        inputs=[task_input, threshold_slider, revisions_slider],
        outputs=[log_output, final_output],
    )


# ------------------------------------------------------------------------------
# 5) LAUNCH  (queue() is required so the streaming generator can update the UI)
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    demo.queue()
    demo.launch(share=False, show_error=True, inbrowser=True)
