# MCP Explorer — Transports & Primitives
### Teal Trust Workshop Interactive Demo

A single Gradio app that teaches all 3 MCP transports and 5 MCP primitives with
live runnable demos, raw JSON-RPC wire messages, and plain-English explanations.

---

## Quick Start

```bash
# 1. Clone / copy this folder into your workspace
cd mcp_explorer

# 2. Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install gradio anthropic mcp python-dotenv

# 4. Set up your API key (only needed for Tab 7 — Sampling)
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY=sk-ant-...

# 5. Run the app
python app.py

# 6. Open http://localhost:7860 in your browser
```

---

## What's Inside

### File Structure
```
mcp_explorer/
├── app.py           ← The entire app — one file, 8 tabs
├── .env.example     ← Copy to .env and add your API key
├── README.md        ← This file
└── requirements.txt ← pip install -r requirements.txt
```

### Tabs

| Tab | Concept | What you see |
|-----|---------|--------------|
| 1 | stdio Transport | Real subprocess, stdin/stdout pipe, live date/time tool |
| 2 | HTTP Transport | Full HTTP POST/response envelope, account balance tool |
| 3 | WebSocket Transport | Persistent session, server PUSH notification |
| 4 | Tools Primitive | tools/list + tools/call, account balance + EMI calculator |
| 5 | Resources Primitive | resources/list + resources/read, KYC policy + customer profile |
| 6 | Prompts Primitive | prompts/list + prompts/get, fillable banking templates |
| 7 | Sampling Primitive | Server asks client's Claude to summarise (real or mock) |
| 8 | Roots Primitive | Client sets URI fence, server checks access |
| 📋 | Quick Reference | One-page cheat sheet with all concepts |

---

## Teaching Notes

### For the instructor
- Every tab is **self-contained** — you can demo any tab in any order.
- The **Quick Reference tab** (last) is ideal as a closing summary.
- Tab 7 (Sampling) is the most conceptually surprising — teach it after Tools.
- The **wire log panel** in each tab shows raw JSON-RPC 2.0 — use it to reinforce
  "same contract, different pipe."

### For learners
- You do **not** need an Anthropic API key for tabs 1–6 and 8.
- Tab 7 (Sampling) works with a mock response if no key is set.
- Read the **Concept Explanation** panel first, then study the **Wire Messages** panel.
- Try changing the inputs and re-running — every run shows fresh JSON-RPC.

---

## The Core Teaching Points

```
1. MCP = JSON-RPC 2.0 messages, always the same shape.

2. Transport = HOW it travels:
   stdio     → same machine, subprocess pipes
   HTTP      → remote URL, POST/response
   WebSocket → remote URL, persistent two-way channel

3. Primitives = WHAT travels through the pipe:
   Tools     (model-controlled)  → DO things
   Resources (app-controlled)    → READ data
   Prompts   (user-controlled)   → GUIDE how to ask
   Sampling  (server asks back)  → BORROW the client's AI
   Roots     (client declares)   → SCOPE the server's access

4. The same JSON-RPC envelope works across all three transports.
   Pick the transport based on where the server lives.
   The primitives don't change regardless of transport.
```

---

## Requirements

```
gradio>=4.0
anthropic>=0.50.0
mcp>=1.2.0
python-dotenv>=1.0.0
```
