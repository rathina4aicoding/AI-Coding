"""
================================================================================
 AGENTIC BUILDING BLOCKS — THE PRIMITIVES, ONE AT A TIME
================================================================================

WHY THIS SCRIPT EXISTS
----------------------
The reflection demos (Basic / Intermediate / Advanced) COMBINE several building
blocks at once, which can make it hard to see each one clearly. This script
shows the three core primitives ON THEIR OWN, each in its own tab, so the class
can understand them separately first. Then the reflection examples make more
sense as "these primitives, composed."

  Tab 1 — PROMPT CHAINING (sequential): output of each step feeds the next.
  Tab 2 — ROUTER (conditional): classify the input, then send it down a
          DIFFERENT path depending on the class.
  Tab 3 — PARALLELIZATION (concurrent): send the same input to several
          independent tasks AT THE SAME TIME and gather the results.

All examples use a simple bank customer-support context. No tools are used.

--------------------------------------------------------------------------------
 HOW TO RUN  (in VS Code)
--------------------------------------------------------------------------------
 1. pip install anthropic gradio python-dotenv
 2. Create a .env file (same folder) with:   CLAUDE_API_KEY=sk-ant-...
 3. python agentic_primitives.py
================================================================================
"""

import os
import time
import anthropic
import gradio as gr
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

# ------------------------------------------------------------------------------
# SETUP — client + a single fast model for the whole demo
# ------------------------------------------------------------------------------
load_dotenv()
api_key = os.environ.get("CLAUDE_API_KEY")
if not api_key:
    raise RuntimeError("CLAUDE_API_KEY not found. Check your .env file.")

client = anthropic.Anthropic(api_key=api_key)
MODEL = "claude-haiku-4-5-20251001"   # fast & cheap is perfect for these demos


def call_claude(system_prompt: str, user_prompt: str, max_tokens: int = 700) -> str:
    """Send one message to Claude and return the plain text reply."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text.strip()


# ==============================================================================
# PRIMITIVE 1 — PROMPT CHAINING  (SEQUENTIAL)
# ==============================================================================
# Three steps run one after another. Each step's OUTPUT becomes the next step's
# INPUT, so the steps are dependent and must run in order:
#
#     message --> [summarise] --> bullets --> [draft] --> reply --> [polish] --> final
# ------------------------------------------------------------------------------

def chain_summarise(message: str) -> str:
    system = ("Summarise the customer's message into 3 concise bullet points "
              "capturing their key concerns. Output only the bullets.")
    return call_claude(system, message)


def chain_draft(bullets: str) -> str:
    system = ("You are a bank support agent. Draft a helpful reply that "
              "addresses each point below. Output only the reply.")
    return call_claude(system, f"Customer's key points:\n{bullets}")


def chain_polish(draft: str) -> str:
    system = ("Rewrite this reply in a warm, professional, concise tone "
              "suitable for a bank. Output only the final version.")
    return call_claude(system, draft)


def run_chain(message: str):
    """Run the three steps in sequence, revealing each as it completes."""
    if not message or not message.strip():
        yield "Please enter a customer message first.", "", ""
        return

    bullets = chain_summarise(message)          # Step 1
    yield bullets, "", ""

    draft = chain_draft(bullets)                # Step 2 (uses Step 1's output)
    yield bullets, draft, ""

    final = chain_polish(draft)                 # Step 3 (uses Step 2's output)
    yield bullets, draft, final


# ==============================================================================
# PRIMITIVE 2 — ROUTER  (CONDITIONAL)
# ==============================================================================
# First we CLASSIFY the message. The category then decides WHICH specialist
# handles it — different category, different path and different system prompt.
#
#                       /--> loan specialist
#     message --> [classify] --> card specialist
#                       \--> account specialist
#                        \--> complaint specialist
# ------------------------------------------------------------------------------

ROUTE_SPECIALISTS = {
    "loan":      "You are a LOANS specialist at a bank.",
    "card":      "You are a CREDIT/DEBIT CARD specialist at a bank.",
    "account":   "You are an ACCOUNTS & DEPOSITS specialist at a bank.",
    "complaint": "You are a COMPLAINTS-RESOLUTION specialist; be empathetic "
                 "and solution-focused.",
}
DEFAULT_ROUTE = "account"


def router_classify(message: str) -> str:
    system = ("Classify the customer message into exactly one category: "
              "loan, card, account, complaint. Respond with ONLY the "
              "category word.")
    raw = call_claude(system, message).strip().lower()
    for category in ROUTE_SPECIALISTS:
        if category in raw:
            return category
    return DEFAULT_ROUTE


def router_respond(category: str, message: str) -> str:
    system = (ROUTE_SPECIALISTS[category]
              + " Draft a concise, helpful response. Output only the response.")
    return call_claude(system, message)


def run_router(message: str):
    """Classify, then dispatch to the matching specialist."""
    if not message or not message.strip():
        return "Please enter a customer message first.", ""

    category = router_classify(message)                 # the conditional step
    response = router_respond(category, message)        # the chosen path
    route_note = (f"### 🧭 Routed to: **{category.upper()} specialist**\n"
                  f"(The classifier picked this path; a different message "
                  f"would take a different one.)")
    return route_note, response


# ==============================================================================
# PRIMITIVE 3 — PARALLELIZATION  (CONCURRENT)
# ==============================================================================
# We send the SAME message to several INDEPENDENT analyses at the same time.
# Because they do not depend on each other, running them concurrently means the
# total wait is about the SLOWEST single call, not the sum of all of them.
#
#                 /--> sentiment   \
#     message --> --> urgency       >  (all at once) --> combine
#                 --> topic        /
#                 \--> next action /
# ------------------------------------------------------------------------------

ANALYSES = {
    "sentiment":   "In ONE short sentence, describe the customer's emotion.",
    "urgency":     "Rate urgency as LOW / MEDIUM / HIGH with a 1-line reason.",
    "topic":       "Name the main banking topic in 2-4 words.",
    "next_action": "Recommend the single best next action for the agent, in "
                   "one sentence.",
}


def run_one_analysis(name: str, message: str):
    """Run one analysis and time how long its API call takes."""
    start = time.time()
    system = f"You are a support-desk analyst. {ANALYSES[name]} Output only the answer."
    result = call_claude(system, message)
    return name, result, time.time() - start


def run_parallel(message: str):
    """Fan the message out to all analyses concurrently and compare timings."""
    if not message or not message.strip():
        return "Please enter a customer message first."

    wall_start = time.time()
    results, durations = {}, {}

    with ThreadPoolExecutor(max_workers=len(ANALYSES)) as executor:
        futures = {executor.submit(run_one_analysis, name, message): name
                   for name in ANALYSES}
        for future in as_completed(futures):
            name, result, elapsed = future.result()
            results[name] = result
            durations[name] = elapsed

    wall_clock = time.time() - wall_start
    seq_estimate = sum(durations.values())   # what one-by-one would have cost

    body = "\n\n".join(f"**{n.upper()}**: {results[n]}" for n in ANALYSES)
    timing = (
        "\n\n---\n"
        f"⏱️ **Parallel wall-clock: {wall_clock:.1f}s**  |  "
        f"Sum of the individual calls (≈ what SEQUENTIAL would cost): "
        f"**{seq_estimate:.1f}s**\n\n"
        "Same work, far less waiting — that is the value of parallelization."
    )
    return body + timing


# ==============================================================================
# GRADIO UI — one tab per primitive
# ==============================================================================

with gr.Blocks(title="Agentic Building Blocks") as demo:
    gr.Markdown(
        "# Agentic Building Blocks — one primitive at a time\n"
        "Each tab shows ONE technique on its own, in a bank support context. "
        "The reflection demos combine all of these."
    )

    # ---- Tab 1: Prompt Chaining (sequential) ----
    with gr.Tab("1 · Prompt Chaining (Sequential)"):
        gr.Markdown(
            "**Sequential:** summarise → draft → polish. Each step's output "
            "feeds the next, so they run in order."
        )
        chain_in = gr.Textbox(label="Customer message", lines=4,
                              placeholder="Paste a rambling customer message…")
        chain_btn = gr.Button("Run the chain", variant="primary")
        with gr.Row():
            chain_out1 = gr.Textbox(label="Step 1 · Key points", lines=8)
            chain_out2 = gr.Textbox(label="Step 2 · Draft reply", lines=8)
            chain_out3 = gr.Textbox(label="Step 3 · Polished final", lines=8)
        gr.Examples(
            examples=[
                ["Hi, I tried to log in to mobile banking three times today and "
                 "it kept failing, then I noticed a charge I don't recognise on "
                 "my statement, and honestly I'm worried someone has my details. "
                 "Can someone help me sort this out quickly?"],
            ],
            inputs=chain_in,
        )
        chain_btn.click(run_chain, inputs=chain_in,
                        outputs=[chain_out1, chain_out2, chain_out3])

    # ---- Tab 2: Router (conditional) ----
    with gr.Tab("2 · Router (Conditional)"):
        gr.Markdown(
            "**Router:** classify the message, then send it to the matching "
            "specialist. Try the different examples to see the route change."
        )
        router_in = gr.Textbox(label="Customer message", lines=4,
                               placeholder="Ask about a loan, a card, an "
                                           "account, or raise a complaint…")
        router_btn = gr.Button("Classify & respond", variant="primary")
        router_route = gr.Markdown(label="Route")
        router_out = gr.Textbox(label="Specialist response", lines=8)
        gr.Examples(
            examples=[
                ["What is the current interest rate on a personal loan and how "
                 "much could I borrow over 3 years?"],
                ["My debit card was declined at a shop even though I have money "
                 "in my account — what's going on?"],
                ["I want to open a fixed deposit. What's the minimum amount and "
                 "tenure options?"],
                ["I've been on hold for 40 minutes twice this week and nobody "
                 "called me back as promised. This is unacceptable."],
            ],
            inputs=router_in,
        )
        router_btn.click(run_router, inputs=router_in,
                         outputs=[router_route, router_out])

    # ---- Tab 3: Parallelization (concurrent) ----
    with gr.Tab("3 · Parallelization (Concurrent)"):
        gr.Markdown(
            "**Parallelization:** analyse the message four independent ways at "
            "once. Watch the timing line — parallel is much faster than the sum."
        )
        par_in = gr.Textbox(label="Customer message", lines=4,
                            placeholder="Paste a customer message to analyse…")
        par_btn = gr.Button("Analyse in parallel", variant="primary")
        par_out = gr.Markdown(label="Analyses + timing")
        gr.Examples(
            examples=[
                ["I URGENTLY need help — my salary was supposed to be credited "
                 "yesterday and it's still not showing, and my rent payment "
                 "bounces tonight. I'm really stressed, please do something!"],
            ],
            inputs=par_in,
        )
        par_btn.click(run_parallel, inputs=par_in, outputs=par_out)


if __name__ == "__main__":
    demo.queue()          # required for the streaming chain tab
    demo.launch()
