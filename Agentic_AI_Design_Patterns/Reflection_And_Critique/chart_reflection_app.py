"""
================================================================================
 REFLECTION & CRITIQUE for CHART GENERATION  (Evaluator–Optimizer, with VISION)
================================================================================

This is the notebook's chart-reflection workflow, rebuilt as a runnable Gradio
app. The twist that makes this pattern special: the EVALUATOR actually *looks
at the rendered chart image* (multimodal), not just the code — exactly how a
human reviewer would critique a first draft.

THE WORKFLOW
------------
  1. GENERATE V1   (Optimizer = Claude Sonnet)
     Sonnet writes matplotlib code for the requested chart, wrapped in
     <execute_python> tags.

  2. EXECUTE V1
     We extract the code from the tags and run it against the DataFrame `df`
     to produce chart_v1.png.

  3. REFLECT  (Evaluator = Claude Opus, WITH VISION)
     We send the actual chart_v1.png IMAGE to Opus. It critiques what it sees
     (clarity, labels, colours, chart type, accuracy) and returns:
       - feedback (JSON)
       - improved matplotlib code (V2) wrapped in <execute_python> tags.

  4. EXECUTE V2
     We run the refined code to produce chart_v2.png.

  [INSTRUCTION] -> Sonnet writes code -> run -> V1 image
                            |
                            v
                   Opus SEES V1 image -> feedback + better code -> run -> V2 image

WHY THESE MODELS
----------------
  * Sonnet (Optimizer): fast, strong code generation — the role we call often.
  * Opus  (Evaluator):  the sharper, vision-capable critic — the quality gate.
This mirrors the Evaluator–Optimizer principle: a stronger model judges, a
cheaper/faster model produces.

--------------------------------------------------------------------------------
 HOW TO RUN  (in VS Code)
--------------------------------------------------------------------------------
 1. pip install anthropic gradio python-dotenv pandas matplotlib
 2. Put your key in a .env file (same folder):   CLAUDE_API_KEY=sk-ant-...
 3. Put coffee_sales.csv in the same folder.
 4. python chart_reflection_app.py

 SAFETY NOTE: this app runs LLM-generated Python via exec(), which is fine for
 a trusted local teaching demo but should never be done with untrusted input
 in production (sandbox it instead).
================================================================================
"""

import os
import re
import json
import base64
import traceback

import anthropic
import gradio as gr
import pandas as pd
import matplotlib
matplotlib.use("Agg")               # headless backend: render to file, no GUI
import matplotlib.pyplot as plt
from dotenv import load_dotenv

# ------------------------------------------------------------------------------
# Setup
# ------------------------------------------------------------------------------
load_dotenv()
api_key = os.environ.get("CLAUDE_API_KEY")
if not api_key:
    raise RuntimeError("CLAUDE_API_KEY not found. Check your .env file.")

client = anthropic.Anthropic(api_key=api_key)

# Optimizer = Sonnet (writes/refines code), Evaluator = Opus (sees + critiques).
OPTIMIZER_MODEL = "claude-sonnet-4-6"
EVALUATOR_MODEL = "claude-opus-4-8"

CSV_PATH = "coffee_sales.csv"

# Column schema we tell the models about. Some columns (year/quarter/month) are
# derived in load_and_prepare_data() so the generated code can use them directly.
SCHEMA_DESCRIPTION = """\
- date        (datetime64 — already parsed; use df['date'].dt.year, etc.)
- time        (string, HH:MM — do NOT concatenate with the date column)
- cash_type   (string: 'card' or 'cash')
- card        (string)
- price       (float)
- coffee_name (string)
- quarter     (int, 1-4 — already computed, use directly)
- month       (int, 1-12 — already computed, use directly)
- year        (int, e.g. 2024 — already computed, use directly)"""


# ------------------------------------------------------------------------------
# Data loading (mirrors the notebook's utils.load_and_prepare_data)
# ------------------------------------------------------------------------------
def load_and_prepare_data(path: str) -> pd.DataFrame:
    """Load the CSV and derive the integer year/quarter/month helper columns."""
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df["quarter"] = df["date"].dt.quarter
    df["month"] = df["date"].dt.month
    return df


# ------------------------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------------------------
def extract_code(text: str) -> str:
    """Pull the python code out of <execute_python>...</execute_python> tags."""
    m = re.search(r"<execute_python>([\s\S]*?)</execute_python>", text)
    return m.group(1).strip() if m else ""


def run_chart_code(code: str, df: pd.DataFrame) -> str:
    """Execute generated matplotlib code with `df` available. Returns '' on
    success, or an error string if the code raised."""
    if not code:
        return "No code was extracted to run."
    try:
        plt.close("all")
        exec(code, {"df": df.copy(), "pd": pd, "plt": plt})
        return ""
    except Exception:
        return traceback.format_exc()


def encode_image_b64(path: str) -> tuple[str, str]:
    """Read an image file and return (media_type, base64-string)."""
    with open(path, "rb") as f:
        data = f.read()
    return "image/png", base64.standard_b64encode(data).decode("utf-8")


def call_text(model: str, prompt: str, max_tokens: int = 1500) -> str:
    """Plain text call (used by the optimizer)."""
    resp = client.messages.create(
        model=model, max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def call_with_image(model: str, prompt: str, img_path: str,
                    max_tokens: int = 1500) -> str:
    """Multimodal call: send an image plus a prompt (used by the evaluator)."""
    media_type, b64 = encode_image_b64(img_path)
    resp = client.messages.create(
        model=model, max_tokens=max_tokens,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": prompt},
            ],
        }],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


# ------------------------------------------------------------------------------
# STEP 1 — Optimizer (Sonnet) generates the first-draft chart code
# ------------------------------------------------------------------------------
def generate_chart_code(instruction: str, out_path: str) -> str:
    prompt = f"""You are a data visualization expert.

Return your answer STRICTLY in this format:

<execute_python>
# valid python code here
</execute_python>

Do not add explanations — only the tags and the code.

The code creates a visualization from a DataFrame `df` with these columns:
{SCHEMA_DESCRIPTION}

User instruction: {instruction}

Requirements:
1. Assume the DataFrame is already loaded as `df`.
2. Use pandas + matplotlib only (no seaborn).
3. Add a clear title, axis labels, and a legend if needed.
4. Save the figure as '{out_path}' with dpi=300 and bbox_inches='tight'.
5. Do NOT call plt.show(). Call plt.close() at the end.
6. Include ALL necessary import statements.
7. CRITICAL: 'date' is datetime64 — never string-concatenate it. Filter by
   year/quarter using the integer 'year' and 'quarter' columns.

Return ONLY the code wrapped in <execute_python> tags."""
    return call_text(OPTIMIZER_MODEL, prompt, max_tokens=1500)


# ------------------------------------------------------------------------------
# STEP 3 — Evaluator (Opus) SEES the V1 chart, critiques it, returns V2 code
# ------------------------------------------------------------------------------
def reflect_and_regenerate(chart_path: str, instruction: str,
                           code_v1: str, out_path_v2: str) -> tuple[str, str]:
    """Returns (feedback_text, refined_code)."""
    prompt = f"""You are a data visualization expert.
Look at the attached chart and critique it against the instruction, then return
improved matplotlib code.

Original code (for context):
{code_v1}

OUTPUT FORMAT (STRICT):
1) First line: a JSON object with ONLY a "feedback" field describing concrete,
   specific visual problems you SEE in the chart (labels, legend, colours,
   chart type, readability, accuracy). Example:
   {{"feedback": "The bars are hard to compare and the legend overlaps the title."}}
2) After a newline, output ONLY the refined Python code wrapped in:
<execute_python>
...
</execute_python>

HARD CONSTRAINTS:
- No markdown, no backticks, no prose outside the two parts above.
- pandas + matplotlib only (no seaborn). Assume `df` already exists.
- Save to '{out_path_v2}' with dpi=300 and bbox_inches='tight'.
- Call plt.close() at the end (no plt.show()). Include all imports.
- 'date' is datetime64: never string-concatenate it; filter via the integer
  'year'/'quarter' columns.

Schema (columns in df):
{SCHEMA_DESCRIPTION}

Instruction:
{instruction}"""

    content = call_with_image(EVALUATOR_MODEL, prompt, chart_path, max_tokens=1800)

    # Parse the feedback JSON (first line, with a regex fallback).
    feedback = ""
    first_line = content.strip().splitlines()[0] if content.strip() else ""
    try:
        feedback = str(json.loads(first_line).get("feedback", "")).strip()
    except Exception:
        m = re.search(r"\{.*?\}", content, flags=re.DOTALL)
        if m:
            try:
                feedback = str(json.loads(m.group(0)).get("feedback", "")).strip()
            except Exception:
                feedback = "(could not parse feedback JSON)"
    if not feedback:
        feedback = "(no feedback returned)"

    refined_code = extract_code(content)
    return feedback, refined_code


# ------------------------------------------------------------------------------
# End-to-end workflow (streams progress to the Gradio UI)
# ------------------------------------------------------------------------------
def run_workflow(instruction: str):
    """Yields UI updates: (status, v1_code, v1_img, feedback, v2_code, v2_img)."""
    blank = (None, "", None, "", "", None)

    if not instruction or not instruction.strip():
        yield ("❗ Please enter a chart instruction.", "", None, "", "", None)
        return

    if not os.path.exists(CSV_PATH):
        yield (f"❌ '{CSV_PATH}' not found. Put it next to this script.",
               "", None, "", "", None)
        return

    df = load_and_prepare_data(CSV_PATH)

    # ---- Step 1: generate V1 code (Sonnet) ----
    yield ("⏳ Step 1/4 — Sonnet is writing the first-draft chart code…",
           "", None, "", "", None)
    raw_v1 = generate_chart_code(instruction, "chart_v1.png")
    code_v1 = extract_code(raw_v1)
    yield ("⏳ Step 2/4 — Running the V1 code…",
           code_v1, None, "", "", None)

    # ---- Step 2: execute V1 ----
    err = run_chart_code(code_v1, df)
    if err:
        yield (f"❌ V1 code failed to run:\n{err}", code_v1, None, "", "", None)
        return
    yield ("⏳ Step 3/4 — Opus is LOOKING at the V1 chart and critiquing it…",
           code_v1, "chart_v1.png", "", "", None)

    # ---- Step 3: reflect (Opus, vision) ----
    feedback, code_v2 = reflect_and_regenerate(
        "chart_v1.png", instruction, code_v1, "chart_v2.png")
    yield ("⏳ Step 4/4 — Running the improved V2 code…",
           code_v1, "chart_v1.png", feedback, code_v2, None)

    # ---- Step 4: execute V2 ----
    err2 = run_chart_code(code_v2, df)
    if err2:
        yield (f"⚠️ Reflection done, but V2 code failed to run:\n{err2}",
               code_v1, "chart_v1.png", feedback, code_v2, None)
        return

    yield ("✅ Done — compare V1 (draft) with V2 (reflected & improved).",
           code_v1, "chart_v1.png", feedback, code_v2, "chart_v2.png")


# ------------------------------------------------------------------------------
# Gradio UI
# ------------------------------------------------------------------------------
with gr.Blocks(title="Chart Reflection — Evaluator/Optimizer") as demo:
    gr.Markdown(
        "# 📊 Chart Generation with Reflection & Critique\n"
        "**Optimizer = Claude Sonnet** writes the chart code · "
        "**Evaluator = Claude Opus** *looks at* the rendered chart and "
        "critiques it, then improves it.\n\n"
        "Enter a question about `coffee_sales.csv` and watch the draft (V1) get "
        "refined into an improved chart (V2)."
    )

    instruction = gr.Textbox(
        label="Chart instruction",
        value="Create a plot comparing Q1 coffee sales in 2024 and 2025 "
              "using the data in coffee_sales.csv.",
        lines=2,
    )
    run_btn = gr.Button("Run reflection workflow", variant="primary")
    status = gr.Markdown("_Ready._")

    gr.Markdown("## Draft vs. Reflected")
    with gr.Row():
        with gr.Column():
            gr.Markdown("### V1 — first draft (Sonnet)")
            v1_img = gr.Image(label="chart_v1.png", height=360)
            v1_code = gr.Code(label="V1 code", language="python")
        with gr.Column():
            gr.Markdown("### V2 — after reflection (Opus critique → Sonnet schema)")
            v2_img = gr.Image(label="chart_v2.png", height=360)
            v2_code = gr.Code(label="V2 code", language="python")

    gr.Markdown("## 🔍 Opus's critique of the V1 chart (what it *saw*)")
    feedback = gr.Markdown("_Run the workflow to see the critique._")

    gr.Examples(
        examples=[
            ["Create a plot comparing Q1 coffee sales in 2024 and 2025 using "
             "the data in coffee_sales.csv."],
            ["Show the top 5 best-selling coffee types by total revenue."],
            ["Plot total monthly revenue across 2024 and 2025 to show the trend."],
            ["Compare the share of card vs cash payments by quarter."],
        ],
        inputs=instruction,
    )

    run_btn.click(
        fn=run_workflow,
        inputs=instruction,
        outputs=[status, v1_code, v1_img, feedback, v2_code, v2_img],
    )


if __name__ == "__main__":
    demo.queue()
    demo.launch(server_name="127.0.0.1", server_port=7860, share=False)
