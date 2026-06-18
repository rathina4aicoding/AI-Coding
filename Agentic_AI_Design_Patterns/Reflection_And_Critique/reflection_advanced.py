"""
================================================================================
 REFLECTION & CRITIQUE  (Evaluator–Optimizer Pattern) — LEVEL 3: ADVANCED
================================================================================

WHAT'S NEW VS. THE INTERMEDIATE VERSION
---------------------------------------
Intermediate used ONE evaluator that gave a single score. Advanced shows how
the reflection pattern composes with the OTHER agentic building blocks you
teach, all in one pipeline:

  1. ROUTER (conditional)      -> First we CLASSIFY the task (customer email /
                                  marketing / internal memo). The category
                                  decides WHICH specialist critics to use.

  2. PARALLEL CRITICS (concurrent) -> Several specialist evaluators — e.g.
                                  CLARITY, TONE, COMPLIANCE — each score ONE
                                  dimension, and they run AT THE SAME TIME
                                  (ThreadPoolExecutor) instead of one-by-one.

  3. AGGREGATION + QUALITY GATE -> We combine the parallel scores. The draft
                                  passes only when EVERY dimension clears the
                                  threshold (the weakest dimension decides).

  4. REFLECTION LOOP            -> If it fails, we revise using the combined
                                  feedback and re-run the parallel critics,
                                  up to a revision budget.

FULL PIPELINE
-------------
  [TASK]
     |
     v
  ROUTER  --(category)-->  pick critic set
     |
     v
  Draft  -->  [ Critic A ] \
              [ Critic B ]  >  run in PARALLEL  --> aggregate --PASS?--+
              [ Critic C ] /                                           |
     ^                                                          NO     | YES
     |                                                          |      v
     +------------------- revise (combined feedback) <----------+   [FINAL]

Same context as before: "improve a piece of writing", now with banking/FS
relevant dimensions like COMPLIANCE.

--------------------------------------------------------------------------------
 HOW TO RUN  (in VS Code)
--------------------------------------------------------------------------------
 1. pip install anthropic gradio python-dotenv
 2. Create a .env file (same folder) with:   CLAUDE_API_KEY=sk-ant-...
 3. python reflection_advanced.py
================================================================================
"""

import os
import re
import json
import anthropic
import gradio as gr
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

# ------------------------------------------------------------------------------
# 1) CLIENT + MODELS
# ------------------------------------------------------------------------------
load_dotenv()
api_key = os.environ.get("CLAUDE_API_KEY")
if not api_key:
    raise RuntimeError("CLAUDE_API_KEY not found. Check your .env file.")

# The Anthropic client is safe to share across threads, which is exactly what
# we need to run several critics in parallel.
client = anthropic.Anthropic(api_key=api_key)

ROUTER_MODEL    = "claude-haiku-4-5-20251001"   # cheap, fast classification
GENERATOR_MODEL = "claude-haiku-4-5-20251001"   # drafts + revisions
EVALUATOR_MODEL = "claude-sonnet-4-6"           # sharper specialist critics


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
# 2) THE SPECIALIST CRITICS  +  THE ROUTING TABLE
# ------------------------------------------------------------------------------
# Each critic focuses on ONE quality dimension. Keeping them separate makes the
# feedback sharper and lets us run them concurrently.
CRITICS = {
    "clarity": "Judge how clear, simple, and easy to understand the writing is. "
               "Flag jargon, long sentences, and ambiguity.",
    "tone": "Judge whether the tone fits the audience: professional, empathetic, "
            "and never threatening or dismissive.",
    "compliance": "Judge accuracy and risk for a banking/financial context: no "
                  "false promises or guarantees, required deadlines/disclaimers "
                  "present, no misleading claims.",
    "completeness": "Judge whether the draft fully addresses every part of the "
                    "task, leaving nothing important out.",
    "persuasiveness": "Judge how compelling and action-driving the writing is "
                      "for a public/marketing audience.",
}

# The ROUTER maps a task category to the set of critics that matter for it.
ROUTES = {
    "customer_email": ["clarity", "tone", "compliance"],
    "marketing":      ["clarity", "persuasiveness", "compliance"],
    "internal":       ["clarity", "completeness"],
}
DEFAULT_ROUTE = "customer_email"   # safe default in a banking context


# ------------------------------------------------------------------------------
# 3) HELPERS: shared parser, generator, reviser  (same idea as before)
# ------------------------------------------------------------------------------

def parse_evaluation(raw: str) -> tuple[int, str]:
    """Pull {"score", "feedback"} out of a critic's JSON reply, safely."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            score = max(1, min(10, int(data.get("score", 5))))
            feedback = str(data.get("feedback", "")).strip()
            return score, feedback or "(no feedback provided)"
        except Exception:
            pass
    return 5, raw  # fallback if not valid JSON


def generate_draft(task: str) -> str:
    """GENERATOR: produce the first draft."""
    system = (
        "You are a helpful writing assistant. Write a clear, focused first "
        "draft for the user's request. Output only the draft, no preamble."
    )
    return call_claude(GENERATOR_MODEL, system, task)


def revise_draft(task: str, draft: str, combined_feedback: str) -> str:
    """OPTIMIZER: rewrite using the combined feedback from all critics."""
    system = (
        "You are a skilled writer. Rewrite the draft to address feedback from "
        "multiple specialist reviewers, prioritising any dimension marked "
        "'NEEDS WORK', while staying true to the original task. "
        "Output only the improved version, no preamble."
    )
    user = (
        f"TASK:\n{task}\n\n"
        f"CURRENT DRAFT:\n{draft}\n\n"
        f"REVIEWER FEEDBACK:\n{combined_feedback}"
    )
    return call_claude(GENERATOR_MODEL, system, user)


# ------------------------------------------------------------------------------
# 4) THE ROUTER  (conditional building block)
# ------------------------------------------------------------------------------

def route_task(task: str) -> str:
    """Classify the task to choose which critic set to apply."""
    system = (
        "You are a router. Classify the writing TASK into exactly one of:\n"
        "- customer_email : a message sent to a customer or client\n"
        "- marketing      : promotional or public-facing content\n"
        "- internal       : a memo/note/update for colleagues\n"
        "Respond with ONLY the category word."
    )
    raw = call_claude(ROUTER_MODEL, system, f"TASK:\n{task}").strip().lower()
    for category in ROUTES:
        if category in raw:
            return category
    return DEFAULT_ROUTE


# ------------------------------------------------------------------------------
# 5) PARALLEL CRITICS  (concurrent building block)
# ------------------------------------------------------------------------------

def run_one_critic(name: str, task: str, draft: str) -> dict:
    """Run a single specialist critic and return {"score", "feedback"}."""
    system = (
        f"You are a specialist evaluator focused ONLY on the dimension: "
        f"{name.upper()}.\n{CRITICS[name]}\n"
        "Score the DRAFT 1-10 for THIS dimension only (10 = excellent). "
        "Respond with ONLY a JSON object: "
        '{"score": <int 1-10>, "feedback": "<specific, actionable suggestions>"}'
    )
    raw = call_claude(EVALUATOR_MODEL, system, f"TASK:\n{task}\n\nDRAFT:\n{draft}")
    score, feedback = parse_evaluation(raw)
    return {"score": score, "feedback": feedback}


def run_critics_in_parallel(task: str, draft: str, critic_names: list) -> dict:
    """Fire all the chosen critics AT THE SAME TIME and collect their verdicts.

    Without threads, 3 critics = 3 sequential API calls. With a thread pool the
    total wait is roughly the time of the SLOWEST single critic, not the sum.
    """
    results = {}
    with ThreadPoolExecutor(max_workers=len(critic_names)) as executor:
        futures = {
            executor.submit(run_one_critic, name, task, draft): name
            for name in critic_names
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as e:
                results[name] = {"score": 5, "feedback": f"(critic error: {e})"}
    return results


def aggregate(results: dict, critic_names: list, threshold: int):
    """Combine parallel scores into a single PASS/REVISE decision.

    Rule: the draft passes only if EVERY dimension meets the threshold — the
    weakest dimension decides. We also build one combined feedback string,
    labelling each dimension OK or NEEDS WORK so the reviser knows what to fix.
    """
    scores = {n: results[n]["score"] for n in critic_names}
    min_score = min(scores.values())
    passed = min_score >= threshold

    lines = []
    for n in critic_names:
        flag = "OK" if results[n]["score"] >= threshold else "NEEDS WORK"
        lines.append(f"[{n.upper()} {results[n]['score']}/10 — {flag}] "
                     f"{results[n]['feedback']}")
    combined = "\n".join(lines)
    return passed, min_score, scores, combined


# ------------------------------------------------------------------------------
# 6) THE FULL PIPELINE  (router -> draft -> parallel critique -> gate -> loop)
# ------------------------------------------------------------------------------

def run_advanced_reflection(task: str, threshold: float, max_revisions: float):
    threshold = int(threshold)
    max_revisions = int(max_revisions)

    if not task or not task.strip():
        yield "Please enter a writing task first.", ""
        return

    log: list[str] = []

    def render() -> str:
        return "\n\n".join(log)

    try:
        # ---- STEP 1: ROUTER (conditional) ----
        category = route_task(task)
        critics = ROUTES[category]
        log.append(
            f"## 🧭 Router\nTask classified as **{category}** → critics: "
            f"{', '.join(c.upper() for c in critics)}"
        )
        yield render(), ""

        # ---- STEP 2: initial draft ----
        draft = generate_draft(task)
        log.append(f"## 📝 Draft 1 (initial)\n{draft}")
        yield render(), draft

        revisions_done = 0
        while True:
            # ---- STEP 3: PARALLEL critics (concurrent) ----
            results = run_critics_in_parallel(task, draft, critics)
            passed, min_score, scores, combined = aggregate(
                results, critics, threshold)

            scoreboard = " | ".join(
                f"{n.upper()}: {scores[n]}/10" for n in critics)
            detail = "\n".join(
                f"- **{n.upper()} {scores[n]}/10**: {results[n]['feedback']}"
                for n in critics)
            verdict = "PASS ✅" if passed else "REVISE 🔁"
            log.append(
                f"## 🔍 Parallel evaluation of Draft {revisions_done + 1}\n"
                f"**Scores:** {scoreboard}\n\n"
                f"**Overall: {verdict}**  (weakest = {min_score}/10, "
                f"threshold = {threshold})\n\n{detail}"
            )
            yield render(), draft

            # ---- STEP 4: QUALITY GATE ----
            if passed:
                log.append(
                    f"## 🏁 Finished — all dimensions passed on attempt "
                    f"{revisions_done + 1}.")
                yield render(), draft
                return
            if revisions_done >= max_revisions:
                log.append(
                    f"## 🏁 Finished — hit the revision budget "
                    f"({max_revisions}). Returning the best effort so far.")
                yield render(), draft
                return

            # ---- STEP 5: REVISE with the combined feedback, then loop ----
            revisions_done += 1
            draft = revise_draft(task, draft, combined)
            log.append(f"## ✍️ Draft {revisions_done + 1} (revised)\n{draft}")
            yield render(), draft

    except Exception as e:
        log.append(f"**Something went wrong:** {e}")
        yield render(), ""


# ------------------------------------------------------------------------------
# 7) GRADIO USER INTERFACE
# ------------------------------------------------------------------------------

with gr.Blocks(title="Reflection & Critique — Advanced") as demo:
    gr.Markdown(
        "# Reflection & Critique — Level 3: Advanced\n"
        "### Router + parallel specialist critics + aggregation gate + loop\n"
        "A **router** picks which critics matter, the critics score the draft "
        "**in parallel** (clarity / tone / compliance …), and the draft is "
        "revised until **every** dimension clears your threshold."
    )

    task_input = gr.Textbox(
        label="Your writing task",
        placeholder=(
            "e.g. Write a 4-line email to a customer whose credit card payment "
            "is overdue, urging payment within 5 days without sounding "
            "threatening, and mentioning a possible late fee."
        ),
        lines=3,
    )

    with gr.Row():
        threshold_slider = gr.Slider(
            minimum=5, maximum=10, value=8, step=1,
            label="Quality threshold (every dimension must reach this)")
        revisions_slider = gr.Slider(
            minimum=1, maximum=4, value=3, step=1,
            label="Max revisions (loop budget)")

    run_button = gr.Button("Run Advanced Reflection", variant="primary")

    with gr.Row():
        log_output = gr.Markdown(label="Pipeline log")
        final_output = gr.Textbox(label="Final version", lines=20)

    gr.Examples(
        examples=[
            # Routes to customer_email -> clarity / tone / compliance
            ["Write a 4-line email to a customer whose credit card payment is "
             "overdue, urging payment within 5 days without sounding "
             "threatening, and mentioning a possible late fee.", 8, 3],
            # Routes to marketing -> clarity / persuasiveness / compliance
            ["Write a punchy promo for a new no-fee savings account aimed at "
             "young professionals. Keep it under 60 words.", 8, 3],
            # Routes to internal -> clarity / completeness
            ["Write an internal memo to the operations team summarising the new "
             "3-step KYC re-verification process and its go-live date.", 8, 3],
        ],
        inputs=[task_input, threshold_slider, revisions_slider],
    )

    run_button.click(
        fn=run_advanced_reflection,
        inputs=[task_input, threshold_slider, revisions_slider],
        outputs=[log_output, final_output],
    )


# ------------------------------------------------------------------------------
# 8) LAUNCH  (queue() enables the streaming log)
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    demo.queue()
    demo.launch(share=False, show_error=True, inbrowser=True)
