# MCP Explorer — Line-by-Line Guide

### A beginner's companion to `mcp_explorer_transports_primitives.ipynb` | Teal Trust Workshop

This guide walks through **every cell** of the notebook and explains **each line** — every
function, class, method, and Python trick — in plain language. It assumes you are new to Python.
Read a cell in the notebook, then read the matching section here.

> **How the notebook is laid out:** the notebook alternates between *markdown cells* (grey text
> boxes that just explain an idea — nothing runs) and *code cells* (which you actually execute with
> **Shift + Enter**). This guide covers both, but spends its detail on the code cells, because that
> is where the line-by-line understanding matters.

---

## Part 0 — Ten Python building blocks that repeat everywhere

Before the cells, here are the ten ideas you will see again and again. Skim them now; refer back
whenever a symbol looks unfamiliar.

**1. Variable and `print`.** `x = 5` stores a value in a name. `print(x)` shows it on screen.

**2. String and f-string.** Text in quotes is a *string*: `"hello"`. An **f-string** starts with
`f` and lets you drop values inside `{}`:
```python
name = "Arjun"
print(f"Hello {name}")     # -> Hello Arjun
```

**3. Dictionary (`dict`).** A labelled bag of values — "key → value" pairs inside `{}`:
```python
person = {"name": "Arjun", "tier": "Gold"}
person["name"]            # -> "Arjun"   (look up by key)
```

**4. List.** An ordered sequence inside `[]`: `["a", "b", "c"]`. `mylist[-1]` is the **last** item.

**5. `.get()` with a default.** A safe way to read a dict key that might be missing:
```python
person.get("age", 0)      # -> 0 if "age" isn't there, instead of crashing
```

**6. List comprehension.** A compact "build a list from another list" loop:
```python
[n * 2 for n in [1, 2, 3]]    # -> [2, 4, 6]
```

**7. `lambda` — a one-line function with no name.**
```python
square = lambda x: x * x
square(4)                  # -> 16
```

**8. `def`, `class`, `self`.** `def` makes a named function. `class` makes a *blueprint* for
objects. Inside a class, `self` means "this particular object." (Full example in Cell 4.)

**9. `try` / `except`.** "Attempt this; if it fails, do that instead" — so one error doesn't stop
the whole program:
```python
try:
    risky_thing()
except Exception:
    print("something went wrong, but we carry on")
```

**10. `**kwargs` unpacking.** A dict can be *unpacked* into function arguments with `**`:
```python
args = {"account_id": "ACC-1"}
get_balance(**args)        # same as  get_balance(account_id="ACC-1")
```

Two more you'll meet once or twice: a **ternary** (`A if condition else B`, a one-line
if/else) and the **`or` default** (`a or b` gives `a` if `a` has a value, otherwise `b`).

---

## The MCP idea in one paragraph

Everything in this notebook is about one message format called **JSON-RPC 2.0**. A *client* sends
a **request** (`{"method": "...", "params": {...}}`); a *server* sends back a **response**
(`{"result": {...}}` or `{"error": {...}}`). **Transports** are *how* that message travels (stdio,
HTTP, WebSocket). **Primitives** are *what* it carries (Tools, Resources, Prompts, Sampling,
Roots). Keep that split in mind and the whole notebook clicks.

---

# Cell 1 — Title *(markdown)*

Just the title and the big picture. Nothing to run. It introduces the "transport vs primitive"
split and lists what the notebook will demo.

---

# Cell 2 — "Setup" heading *(markdown)*

Explains that the notebook needs only Python's standard library plus two optional packages, and
that it *warns* instead of quitting when there's no API key. Nothing to run.

---

# Cell 3 — Imports *(code)*

**What it does:** loads the tools this notebook needs from Python's standard library, and
optionally reads a `.env` file.

```python
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from datetime import datetime
from typing import Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

print("Core imports ready (standard library).")
```

- `from __future__ import annotations` — a compatibility line. It lets us write modern type hints
  (like `dict[str, dict]`, which you'll see later) without errors on slightly older Python
  versions. You can treat it as boilerplate that goes at the very top.
- `import json` — the **JSON** toolkit. JSON is the text format all MCP messages use. We'll use
  `json.dumps` (Python object → JSON text) and `json.loads` (JSON text → Python object).
- `import os` — talks to the **operating system**; here we use `os.getenv(...)` to read
  environment variables (like the API key).
- `import subprocess` — lets Python **launch other programs**. We use it for the real stdio demo,
  where the notebook starts a second Python program.
- `import sys` — **system** helpers; we use `sys.executable`, which is the path to the exact Python
  running this notebook.
- `import textwrap` — text formatting; `textwrap.dedent(...)` removes the leading indentation from
  a block of text so multi-line strings print cleanly.
- `from datetime import datetime` — pulls the `datetime` clock tool out of the `datetime` module,
  so we can write `datetime.now()`.
- `from typing import Any` — `Any` is a *type hint* meaning "any type at all." Type hints are just
  labels for humans and tools; they don't change how the code runs.
- `try: / from dotenv import load_dotenv / load_dotenv() / except Exception: / pass` — **optional
  convenience.** If the `python-dotenv` package is installed, `load_dotenv()` reads a `.env` file
  and loads its `KEY=value` lines into the environment. If the package is *not* installed, the
  `except Exception: pass` swallows the error and we simply move on. `pass` means "do nothing."
- `print("Core imports ready ...")` — a confirmation message so you know the cell finished.

> 🐍 **New idea — `import`.** `import X` loads a toolbox; `from X import Y` grabs one specific tool
> `Y` out of it so you can use `Y` directly.

---

# Cell 4 — API key and optional Claude client *(code)*

**What it does:** finds an API key if one exists, picks a model name, and creates a Claude client
*only* if a key is present. Without a key, everything still runs — only the Sampling demo later
falls back to a mock.

```python
API_KEY = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY", "")

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

try:
    from anthropic import Anthropic
    anthropic_client = Anthropic(api_key=API_KEY) if API_KEY else None
except Exception:
    anthropic_client = None

if API_KEY and anthropic_client:
    print(f"API key found — the Sampling demo will call real Claude ({MODEL}).")
else:
    print("No API key found — the Sampling demo will use a mock response.")
    print("Every other cell in this notebook runs without a key.")
```

- `API_KEY = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY", "")` — read the key from
  the environment. `os.getenv("NAME")` returns the value, or `None` if it isn't set. The **`or`**
  means: *try the first name; if that's empty, try the second.* The `""` in the second call is a
  default (empty string) so `API_KEY` is never `None`.
- `MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")` — read a model name from the
  environment, but if it isn't set, use `"claude-sonnet-4-6"` as the default.
- `try: from anthropic import Anthropic` — attempt to load the Anthropic library. It's optional, so
  this is guarded by `try`.
- `anthropic_client = Anthropic(api_key=API_KEY) if API_KEY else None` — a **ternary** (one-line
  if/else). Read it as: "*create* an `Anthropic` client **if** `API_KEY` has a value, **otherwise**
  set `anthropic_client` to `None`." An empty string is treated as "no value," so no key → `None`.
- `except Exception: anthropic_client = None` — if the library isn't installed at all, don't crash;
  just record that we have no client.
- `if API_KEY and anthropic_client:` — both must be truthy (a key *and* a working client) to say
  "real Claude is available." `and` means both conditions must hold.
- The `print(f"... ({MODEL}).")` line is an f-string, so `{MODEL}` is replaced by the model name.
- The `else:` branch runs when there's no usable key, printing the "mock" reassurance.

> 🐍 **New idea — truthy / falsy.** Python treats `None`, `""` (empty string), `0`, and empty
> collections as **falsy** (like "false"); most other values are **truthy**. That's why
> `x or default` and `if API_KEY:` work the way they do.

---

# Cell 5 — "The JSON-RPC 2.0 envelope" *(markdown)*

Explains the two message shapes (request and response) with small JSON examples. Nothing to run —
it sets up the next code cell.

---

# Cell 6 — Helper functions *(code)*

**What it does:** defines five small reusable functions — the toolkit the whole notebook leans on —
then prints two example messages.

```python
def _pretty(obj: Any) -> str:
    """Pretty-print any JSON-serialisable object (what you'd see on the wire)."""
    return json.dumps(obj, indent=2, default=str)


def jsonrpc_request(method: str, params: dict, req_id: int = 1) -> dict:
    """Build a well-formed JSON-RPC 2.0 REQUEST."""
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}


def jsonrpc_result(req_id: int, result: Any) -> dict:
    """Build a well-formed JSON-RPC 2.0 SUCCESS response."""
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def jsonrpc_error(req_id: int, code: int, message: str) -> dict:
    """Build a well-formed JSON-RPC 2.0 ERROR response."""
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def show_step(label: str, payload: dict) -> None:
    """Print one message exactly as it travels on the wire — the teaching centrepiece."""
    print(f"── {label} ──")
    print(_pretty(payload))
    print()


show_step("Example REQUEST  (client -> server)", jsonrpc_request("tools/list", {}, 1))
show_step("Example RESPONSE (server -> client)", jsonrpc_result(1, {"tools": ["..."]}))
```

**Reading a function definition.** `def name(inputs) -> output_type:` starts a function. The
indented lines below it are its body. The `"""triple-quoted"""` first line is a **docstring** —
a human description. `return` hands a value back to whoever called the function.

- **`_pretty(obj)`** — turns any Python object into nicely indented JSON *text*.
  - `json.dumps(obj, indent=2, default=str)` — `dumps` = "dump to string." `indent=2` adds 2-space
    indentation so it's readable. `default=str` is a safety net: if something can't be turned into
    JSON directly (like a date), convert it to text with `str(...)` instead of crashing.
  - The leading underscore in `_pretty` is a **convention** meaning "internal helper." It still
    works like any function.
- **`jsonrpc_request(method, params, req_id=1)`** — builds a request dictionary. `req_id=1` is a
  **default value**: if the caller doesn't pass an id, it's `1`. The function just returns a dict
  with the four required JSON-RPC keys: `jsonrpc`, `id`, `method`, `params`.
- **`jsonrpc_result(req_id, result)`** — builds a *success* response dict (`result` key).
- **`jsonrpc_error(req_id, code, message)`** — builds a *failure* response dict. Notice `error` is
  itself a small dict with `code` and `message` inside it — a dictionary nested in a dictionary.
- **`show_step(label, payload)`** — the print helper you'll see in every demo. `-> None` means it
  returns nothing; it just prints. It prints a header line with the label, then the pretty JSON,
  then an empty `print()` for a blank spacer line.
- The final two lines **call** `show_step` with example messages so you see the shapes immediately.
  `jsonrpc_request("tools/list", {}, 1)` builds a request whose params is an empty dict `{}`.

> 🐍 **New idea — default argument.** In `def f(x, y=1):`, `y` is optional; if you call `f(5)`,
> then `y` is `1`. That's why `jsonrpc_request("tools/list", {})` works without a third argument.

---

# Cell 7 — "A mini in-process MCP server" *(markdown)*

Explains that instead of a real separate program, we use a tiny server living inside the notebook
so the protocol stays visible. Nothing to run.

---

# Cell 8 — The `MiniMCPServer` class *(code)*

**What it does:** defines the server — a class that can *register* tools/resources/prompts and
*answer* JSON-RPC requests through one method, `handle`.

### The class shell and `__init__`

```python
class MiniMCPServer:
    """A tiny, self-contained MCP server ... The single entry point a client talks to is handle()."""

    def __init__(self, name: str = "MiniServer"):
        self.name = name
        self._tools: dict[str, dict] = {}
        self._resources: dict[str, Any] = {}
        self._prompts: dict[str, dict] = {}
        self._roots: list[dict] = []
```

- `class MiniMCPServer:` — defines a **blueprint** for making server objects. Think of a class as a
  cookie cutter and each object you create from it as a cookie.
- `def __init__(self, name="MiniServer"):` — the **constructor**. Python runs it automatically when
  you create an object. `self` is "the object being built." `name="MiniServer"` is a default name.
- `self.name = name` — store the name *on this object* so we can use it later.
- `self._tools = {}` (and `_resources`, `_prompts`) — start empty dictionaries that will hold
  whatever gets registered. `self._roots = []` starts an empty list. The `: dict[str, dict]` parts
  are just type-hint labels ("a dict whose keys are strings and values are dicts").

### The registration helpers

```python
    def register_tool(self, name, description, schema, fn):
        self._tools[name] = {"description": description, "inputSchema": schema, "fn": fn}

    def register_resource(self, uri, description, value):
        self._resources[uri] = {"description": description, "value": value}

    def register_prompt(self, name, description, template, args):
        self._prompts[name] = {"description": description, "template": template, "arguments": args}
```

- Each of these is a **method** (a function that lives inside a class; its first parameter is always
  `self`).
- `register_tool` stores a tool under its name. The value is a dict holding a `description`, an
  `inputSchema` (a description of the tool's inputs), and — importantly — `fn`, the **actual Python
  function** to run when the tool is called. Yes: a function can be stored inside a dictionary.
- `register_resource` stores read-only data under a URI (a web-address-like key).
- `register_prompt` stores a reusable text template plus the list of argument names it expects.

### The heart: `handle`

```python
    def handle(self, request: dict) -> dict:
        method = request.get("method", "")
        rid = request.get("id", 0)
        params = request.get("params") or {}
```

- `handle(self, request)` — the **one door** a client knocks on. You hand it a request dict; it
  returns a response dict.
- `method = request.get("method", "")` — pull the `method` name out of the request; if it's
  missing, use `""`. Using `.get()` (instead of `request["method"]`) avoids a crash on a malformed
  request.
- `rid = request.get("id", 0)` — the request's id, defaulting to `0`.
- `params = request.get("params") or {}` — the arguments. The `or {}` guard means: if `params` is
  missing *or* `None`, use an empty dict instead.

```python
        if method == "initialize":
            return jsonrpc_result(rid, {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": self.name, "version": "1.0.0"},
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
            })
```

- This is the start of a big **`if / elif / else` switchboard**: "which method was asked for?"
- For `"initialize"` (the handshake), it returns a success response describing the server: its
  protocol version, its name/version, and what it can do (`capabilities`).

```python
        elif method == "tools/list":
            tools = [
                {"name": n, "description": d["description"], "inputSchema": d["inputSchema"]}
                for n, d in self._tools.items()
            ]
            return jsonrpc_result(rid, {"tools": tools})
```

- `elif` = "else, if" — checked only when the earlier conditions were false.
- The `[ ... for n, d in self._tools.items() ]` is a **list comprehension**. `self._tools.items()`
  walks the tools dictionary, giving each name `n` and its detail dict `d`. For each one it builds a
  small public dict (name + description + input schema — but *not* the private `fn`). The result is
  a list of tool descriptions, returned under `{"tools": ...}`.

```python
        elif method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments", {})
            if name not in self._tools:
                return jsonrpc_error(rid, -32601, f"Tool '{name}' not found")
            try:
                result = self._tools[name]["fn"](**args)
                return jsonrpc_result(rid, {"content": [{"type": "text", "text": str(result)}], "isError": False})
            except Exception as exc:
                return jsonrpc_result(rid, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
```

- This is where a tool actually runs.
- `name = params.get("name", "")` and `args = params.get("arguments", {})` — read which tool to run
  and the arguments to pass it.
- `if name not in self._tools:` — if that tool was never registered, return a JSON-RPC error (code
  `-32601` is the standard "method not found" code).
- `result = self._tools[name]["fn"](**args)` — the key line. `self._tools[name]["fn"]` fetches the
  stored function; `(**args)` **unpacks** the args dict into keyword arguments and calls it. If
  `args` is `{"account_id": "ACC-1"}`, this runs `fn(account_id="ACC-1")`.
- On success it wraps the result as MCP text content with `"isError": False`.
- `except Exception as exc:` — if the tool function throws an error, we *catch* it (as `exc`),
  convert it to text, and return `"isError": True` instead of crashing the whole notebook.

```python
        elif method == "resources/list":
            resources = [
                {"uri": uri, "description": d["description"]}
                for uri, d in self._resources.items()
            ]
            return jsonrpc_result(rid, {"resources": resources})

        elif method == "resources/read":
            uri = params.get("uri", "")
            if uri not in self._resources:
                return jsonrpc_error(rid, -32601, f"Resource '{uri}' not found")
            value = self._resources[uri]["value"]
            text = _pretty(value) if not isinstance(value, str) else value
            return jsonrpc_result(rid, {"contents": [{"uri": uri, "mimeType": "text/plain", "text": text}]})
```

- `resources/list` mirrors `tools/list`: it comprehends the resources dict into a list of
  `{uri, description}` entries.
- `resources/read` looks up one resource by its `uri`. If missing → error.
- `value = self._resources[uri]["value"]` — grab the stored data.
- `text = _pretty(value) if not isinstance(value, str) else value` — another ternary.
  `isinstance(value, str)` asks "is this value already text?" If it *is* a string, keep it as-is;
  if it's a dict (like the customer profile), pretty-print it into JSON text first. This guarantees
  the response always carries readable text.

```python
        elif method == "prompts/list":
            prompts = [
                {"name": n, "description": d["description"],
                 "arguments": [{"name": a, "required": True} for a in d["arguments"]]}
                for n, d in self._prompts.items()
            ]
            return jsonrpc_result(rid, {"prompts": prompts})
```

- `prompts/list` has a **comprehension inside a comprehension**. The outer one walks every prompt.
  The inner one — `[{"name": a, "required": True} for a in d["arguments"]]` — turns each argument
  name `a` into a small `{name, required}` dict. So each prompt is reported with its name,
  description, and the list of arguments it needs.

```python
        elif method == "prompts/get":
            name = params.get("name", "")
            args = params.get("arguments", {})
            if name not in self._prompts:
                return jsonrpc_error(rid, -32601, f"Prompt '{name}' not found")
            filled = self._prompts[name]["template"]
            for k, v in args.items():
                filled = filled.replace(f"{{{k}}}", str(v))
            return jsonrpc_result(rid, {
                "description": self._prompts[name]["description"],
                "messages": [{"role": "user", "content": {"type": "text", "text": filled}}],
            })
```

- This **fills in a template**. `filled` starts as the raw template text, e.g.
  `"Summarise the last {days} days for account {account_id}."`
- `for k, v in args.items():` — loop over each argument, where `k` is the key (like `"days"`) and
  `v` is the value (like `"30"`).
- `filled = filled.replace(f"{{{k}}}", str(v))` — the important trick. In an f-string, `{{` means a
  literal `{` and `}}` means a literal `}`. So `f"{{{k}}}"` builds the text `{days}` (a real brace,
  the key's value, a real brace). `.replace(...)` swaps every `{days}` in the template for `30`.
  After the loop, all placeholders are filled.
- It returns the filled text as a ready-to-send chat message (`role: user`).

```python
        elif method == "roots/list":
            return jsonrpc_result(rid, {"roots": self._roots})

        elif method == "sampling/createMessage":
            return jsonrpc_result(rid, {"__sampling_request__": True, "params": params})

        else:
            return jsonrpc_error(rid, -32601, f"Unknown method: {method}")


print("MiniMCPServer defined.")
```

- `roots/list` simply hands back whatever roots the client declared (used in the Roots demo).
- `sampling/createMessage` returns a marker saying "this needs the client's AI" — the real work
  happens in the Sampling demo cell.
- `else:` — any method we don't recognise returns a "method not found" error.
- After the class definition ends, `print("MiniMCPServer defined.")` confirms it loaded. Defining a
  class doesn't run any of its methods yet — it just teaches Python the blueprint.

> 🐍 **New idea — class vs object.** The `class` is the blueprint. You haven't made a server yet;
> you do that in the next cell with `server = MiniMCPServer(...)`. Each call to `MiniMCPServer(...)`
> makes a fresh, independent object.

---

# Cell 9 — "Register the banking primitives" *(markdown)*

Lists the tools, resources, and prompts we're about to register. Nothing to run.

---

# Cell 10 — Build and populate the banking server *(code)*

**What it does:** creates one server object and fills it with two tools, two resources, and two
prompts — the banking surface used by every later demo.

```python
server = MiniMCPServer("BankingMCPServer")
```

- Creates the actual server object from the blueprint and names it `"BankingMCPServer"`. From now
  on, `server` is the thing every demo talks to.

```python
server.register_tool(
    "get_account_balance",
    "Return the mock balance for a given account number.",
    {"type": "object",
     "properties": {"account_id": {"type": "string", "description": "Account number"}},
     "required": ["account_id"]},
    lambda account_id: f"Account {account_id}: Balance = INR {(hash(account_id) % 90000) + 10000:,}.00",
)
```

- Calls the `register_tool` method with four things: the tool's **name**, a **description**, an
  **input schema** (a dict saying "this tool takes one required string called `account_id`"), and
  the **function** to run.
- The function is a **`lambda`** — a one-line unnamed function. `lambda account_id: ...` takes an
  `account_id` and returns an f-string.
- Inside the f-string: `hash(account_id)` turns the text into some number; `% 90000` keeps it in the
  range 0–89,999; `+ 10000` shifts it to 10,000–99,999 — a believable fake balance. The `:,` inside
  `{...:,}` formats the number with thousands separators (e.g. `52,340`). This is a *mock* — it
  stands in for a real database lookup, and the number may differ between sessions.

```python
server.register_tool(
    "calculate_emi",
    "Calculate monthly EMI for a loan.",
    {"type": "object",
     "properties": {"principal": {"type": "number"},
                    "annual_rate": {"type": "number", "description": "Annual interest rate (%)"},
                    "months": {"type": "integer"}},
     "required": ["principal", "annual_rate", "months"]},
    lambda principal, annual_rate, months: (
        f"EMI = INR {principal * (annual_rate/1200) * (1 + annual_rate/1200)**months / ((1 + annual_rate/1200)**months - 1):,.2f} / month"
    ),
)
```

- A second tool, `calculate_emi`, whose schema declares three required numbers.
- The lambda computes the standard EMI (equated monthly instalment) formula. Two details worth
  knowing: `annual_rate/1200` converts an annual percentage into a monthly fraction (divide by 100
  for percent, then by 12 for months = 1200); `**` means "to the power of," so `(1 + r)**months`
  is compound growth over the loan term. The `:,.2f` formats the result with thousands separators
  and exactly 2 decimal places.

```python
server.register_resource(
    "bank://policies/kyc-rules",
    "KYC compliance rules document",
    "KYC Rules v3.2: 1) Govt-issued photo ID required. ...",
)
server.register_resource(
    "bank://customers/C001/profile",
    "Customer profile for C001",
    {"id": "C001", "name": "Arjun Sharma", "tier": "Gold", "since": "2019-03-15", "branch": "Chennai-OMR"},
)
```

- Two **resources** (read-only data). The first stores a plain **string** (a policy document). The
  second stores a **dict** (a customer profile). Remember Cell 8's `resources/read` handled both
  cases: strings pass through, dicts get pretty-printed to text.

```python
server.register_prompt(
    "summarize_account_activity",
    "Generate a summary prompt for a customer's recent account activity.",
    "Summarise the last {days} days of activity for account {account_id}. ...",
    ["account_id", "days"],
)
server.register_prompt(
    "draft_loan_decision_letter",
    "Draft a formal loan decision letter.",
    "Draft a formal letter to customer {customer_name} regarding their loan application for INR {loan_amount}. Decision: {decision}. ...",
    ["customer_name", "loan_amount", "decision"],
)
```

- Two **prompts** (reusable templates). Note the `{days}`, `{account_id}`, etc. — those are the
  placeholders that `prompts/get` fills in. The final argument is a **list** of the placeholder
  names the template expects.

```python
print("BankingMCPServer ready.")
print("  Tools    :", list(server._tools))
print("  Resources:", list(server._resources))
print("  Prompts  :", list(server._prompts))
```

- Confirmation output. `list(server._tools)` turns the tools dictionary into a list of just its
  **keys** (the tool names), so you can see what got registered.

> 🐍 **New idea — a function as data.** Storing a `lambda` inside the server is the whole trick that
> makes a "tool" work: the server keeps the function until a `tools/call` arrives, then runs it.

---

# Cell 11 — "Talk to the server by hand" *(markdown)*

Explains that we'll send one raw handshake request before using any transport. Nothing to run.

---

# Cell 12 — The handshake, by hand *(code)*

**What it does:** sends a single `initialize` request straight into the server and prints the
request and response.

```python
init_req = jsonrpc_request("initialize",
                           {"protocolVersion": "2024-11-05", "clientInfo": {"name": "explorer"}}, 1)
print("REQUEST :", json.dumps(init_req))
print("RESPONSE:")
print(_pretty(server.handle(init_req)))
```

- `init_req = jsonrpc_request(...)` — build an `initialize` request using our helper from Cell 6.
  The params include a protocol version and some info about the client.
- `print("REQUEST :", json.dumps(init_req))` — `print` can take several items separated by commas;
  it prints them with spaces between. `json.dumps(init_req)` shows the request as one line of JSON.
- `server.handle(init_req)` — hand the request to the server's one door. It returns the response
  dict, which `_pretty(...)` formats before printing. This is the handshake, fully visible.

---

# Cell 13 — "Part A — Transports" *(markdown)*

Section header with the transports comparison table. Nothing to run.

---

# Cell 14 — "A1 · stdio transport" *(markdown)*

Explains stdio (two text streams, no network) with the "passing notes" analogy. Nothing to run.

---

# Cell 15 — Write the standalone stdio server to disk *(code)*

**What it does:** stores a *complete* second Python program as a big string, writes it to a file,
and prints it.

```python
STDIO_SERVER_CODE = r"""
# stdio_datetime_server.py
...
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    sys.stdout.write(json.dumps(handle(json.loads(line))) + "\n")
    sys.stdout.flush()
"""

with open("stdio_datetime_server.py", "w") as f:
    f.write(STDIO_SERVER_CODE)

print("Wrote stdio_datetime_server.py -- a real, standalone MCP server. Source:")
print(STDIO_SERVER_CODE)
```

- `STDIO_SERVER_CODE = r"""..."""` — a **triple-quoted string** can span many lines, so we store an
  entire program as text. The leading `r` makes it a **raw string**, so backslashes (like the `\n`
  inside it) are kept literally rather than interpreted here.
- Inside that program (this is the *server's* code, which will run in its own process):
  - `for line in sys.stdin:` — read input **one line at a time** from standard input (the pipe the
    client writes to). This loop pauses and waits whenever there's nothing to read.
  - `line = line.strip()` — remove surrounding whitespace/newline.
  - `if not line: continue` — if the line is empty, skip to the next loop turn (`continue`).
  - `sys.stdout.write(json.dumps(handle(json.loads(line))) + "\n")` — read innermost-first:
    `json.loads(line)` parses the incoming JSON text into a Python dict → `handle(...)` processes it
    → `json.dumps(...)` turns the response back into JSON text → `+ "\n"` adds a newline so the
    client knows the message ended → `sys.stdout.write(...)` sends it back out the pipe.
  - `sys.stdout.flush()` — **push the text out now.** Without flushing, the message can sit in a
    buffer and the client waits forever. This is a classic beginner gotcha with pipes.
- `with open("stdio_datetime_server.py", "w") as f:` — open a file for **w**riting. The `with`
  block automatically closes the file when it ends (even if something errors). `as f` names the open
  file `f`.
- `f.write(STDIO_SERVER_CODE)` — write the whole program text into that file.
- The two `print(...)` lines confirm the write and display the server's source so students can read
  it.

> 🐍 **New idea — `with ... as`.** This is a *context manager*. It's the tidy way to open a file:
> it guarantees the file is closed afterwards so you don't leak resources.

---

# Cell 16 — "Now the client side" *(markdown)*

A short note that the next cell launches that file as a real subprocess. Nothing to run.

---

# Cell 17 — Run the stdio server as a real subprocess *(code)*

**What it does:** launches the server file as a separate program and exchanges real JSON-RPC lines
with it over pipes.

```python
date_format = "%d %B %Y - %I:%M %p"

proc = subprocess.Popen(
    [sys.executable, "stdio_datetime_server.py"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
)
```

- `date_format = "..."` — the one **interactive knob**: a `strftime` pattern controlling how the
  date is formatted. Change it and re-run to see different output.
- `proc = subprocess.Popen([...], ...)` — **start another program.** The list
  `[sys.executable, "stdio_datetime_server.py"]` is literally the command line: "run *this* Python
  on *that* file." `sys.executable` is the current Python's path, so the child uses the same Python.
  - `stdin=subprocess.PIPE` — create a pipe we can **write** into (the child's input).
  - `stdout=subprocess.PIPE` — create a pipe we can **read** from (the child's output).
  - `stderr=subprocess.PIPE` — capture the child's error stream too.
  - `text=True` — send/receive normal strings instead of raw bytes.
  - `proc` is a handle to the running child process.

```python
def stdio_send(req):
    """Write one JSON-RPC line to the child's stdin, read one line back from its stdout."""
    show_step("-> CLIENT sends (stdin)", req)
    proc.stdin.write(json.dumps(req) + "\n")
    proc.stdin.flush()
    resp = json.loads(proc.stdout.readline())
    show_step("<- SERVER responds (stdout)", resp)
    return resp
```

- A small helper defined *inside* this cell so it can use `proc`.
- `show_step("-> CLIENT sends (stdin)", req)` — print what we're about to send.
- `proc.stdin.write(json.dumps(req) + "\n")` — turn the request dict into JSON text, add a newline,
  and write it into the child's input pipe.
- `proc.stdin.flush()` — push it through immediately (same reason as before).
- `resp = json.loads(proc.stdout.readline())` — `readline()` waits for and reads one line of the
  child's output; `json.loads(...)` parses that JSON text back into a Python dict.
- It prints the response and returns it.

```python
stdio_send(jsonrpc_request("initialize",
                           {"protocolVersion": "2024-11-05", "clientInfo": {"name": "explorer"}}, 1))
stdio_send(jsonrpc_request("tools/list", {}, 2))
final = stdio_send(jsonrpc_request("tools/call",
                                   {"name": "get_current_datetime",
                                    "arguments": {"date_format": date_format}}, 3))

proc.stdin.close()
proc.wait(timeout=5)

print("RESULT:", final["result"]["content"][0]["text"])
print("\nSame JSON-RPC you saw in-process -- now across a real subprocess pipe.")
```

- Three real round-trips over the pipe: the handshake (`initialize`), discovery (`tools/list`), and
  a call (`tools/call`) passing the `date_format`. Each uses `jsonrpc_request(...)` with ids 1, 2, 3.
- `final = stdio_send(...)` — keep the last response so we can read the answer out of it.
- `proc.stdin.close()` — close the input pipe; this signals the child "no more requests," so its
  `for line in sys.stdin` loop ends.
- `proc.wait(timeout=5)` — wait (up to 5 seconds) for the child program to finish cleanly.
- `final["result"]["content"][0]["text"]` — dig into the nested response: `["result"]` →
  `["content"]` (a list) → `[0]` (its first item) → `["text"]` (the actual date string). Reading
  nested dicts/lists like this is very common when handling JSON.

> 🐍 **New idea — a subprocess.** This cell is genuinely running *two programs*: the notebook (the
> client) and `stdio_datetime_server.py` (the server), talking over pipes. That's exactly how real
> MCP tools like Claude Desktop's work.

---

# Cell 18 — "A2 · HTTP transport" *(markdown)*

Explains HTTP (the server at a URL, POST a request, get a JSON reply) with the "posting a letter"
analogy. Nothing to run.

---

# Cell 19 — HTTP transport demo *(code)*

**What it does:** shows the exact HTTP envelope that would wrap a JSON-RPC message, while processing
the message with our in-process server so the focus stays on the message shape.

```python
account_id = "ACC-BANK-001"

req = jsonrpc_request("tools/call",
                      {"name": "get_account_balance", "arguments": {"account_id": account_id}}, 1)

http_request = textwrap.dedent(f"""\
    POST /mcp HTTP/1.1
    Host: api.mybank.com
    Content-Type: application/json
    Authorization: Bearer <token>

    {_pretty(req)}""")

server.handle(jsonrpc_request("initialize", {}, 0))
resp = server.handle(req)

http_response = textwrap.dedent(f"""\
    HTTP/1.1 200 OK
    Content-Type: application/json

    {_pretty(resp)}""")

print("== HTTP REQUEST  (client -> server) ==")
print(http_request)
print("\n== HTTP RESPONSE (server -> client) ==")
print(http_response)
print("\nRESULT:", resp["result"]["content"][0]["text"])
```

- `account_id = "ACC-BANK-001"` — the interactive knob for this demo.
- `req = jsonrpc_request("tools/call", {...}, 1)` — build the same kind of tool-call request you've
  seen before. **The JSON-RPC body is identical to stdio's** — only the wrapper changes.
- `http_request = textwrap.dedent(f"""\ ... """)` — build the text of an HTTP request. The `f`
  makes it an f-string so `{_pretty(req)}` drops the JSON body in. The backslash `\` right after the
  opening `"""` avoids a blank first line. `textwrap.dedent(...)` strips the shared leading spaces so
  it prints flush-left. Those `POST`, `Host`, `Content-Type`, `Authorization` lines are standard
  HTTP headers.
- `server.handle(jsonrpc_request("initialize", {}, 0))` — do a quick handshake first (its return
  value is ignored here).
- `resp = server.handle(req)` — actually process the request and keep the response.
- `http_response = textwrap.dedent(...)` — build the text of the HTTP *reply*, with `200 OK` (the
  standard "success" status) and the JSON body.
- The `print(...)` lines display the request envelope, the response envelope, and the extracted
  result text.

> 🐍 **New idea — same message, new wrapper.** Notice we never started a real web server. The point
> is visual: the JSON-RPC in the HTTP body is the very same object; only the envelope differs from
> stdio.

---

# Cell 20 — "A3 · WebSocket transport" *(markdown)*

Explains WebSockets (one always-open connection, both sides can talk anytime, the server can PUSH)
with the "phone off the hook" analogy. Nothing to run.

---

# Cell 21 — WebSocket transport demo *(code)*

**What it does:** simulates a persistent two-way session and highlights the one thing only
WebSockets can do — the server pushing a message with no request.

```python
topic = "FX rates"

conversation = []
def ws_log(direction, payload):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    conversation.append((ts, direction, payload))
```

- `topic = "FX rates"` — the interactive knob; it appears inside the server's push message.
- `conversation = []` — an empty list that will collect every message, in order.
- `def ws_log(direction, payload):` — a helper to record one message.
  - `ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]` — the current time. `%f` gives microseconds
    (6 digits); `[:-3]` slices off the last 3 characters to leave milliseconds (3 digits). `[:-3]`
    means "everything except the final three characters."
  - `conversation.append((ts, direction, payload))` — add a **tuple** `(time, direction, message)`
    to the list. A tuple is just a fixed group of values in `()`.

```python
init_req = jsonrpc_request("initialize",
                           {"protocolVersion": "2024-11-05", "clientInfo": {"name": "ws-explorer"}}, 1)
ws_log("CLIENT -> SERVER", init_req)
ws_log("SERVER -> CLIENT", server.handle(init_req))

list_req = jsonrpc_request("tools/list", {}, 2)
ws_log("CLIENT -> SERVER", list_req)
ws_log("SERVER -> CLIENT", server.handle(list_req))
```

- The client initialises and lists tools, and we log **both directions** each time: the request we
  send, and the response `server.handle(...)` gives back.

```python
ws_log("SERVER -> CLIENT  (PUSH - no request!)", {
    "jsonrpc": "2.0",
    "method": "notifications/tools/list_changed",
    "params": {"message": f"New tool added related to '{topic}' - please re-list!"},
})
```

- The star of the demo: a **server push**. Notice this message has a `method` but **no `id`** and
  came with **no matching request** — the server volunteered it. That's the WebSocket-only feature.
  The `f"...'{topic}'..."` f-string drops your `topic` into the message.

```python
call_req = jsonrpc_request("tools/call",
                           {"name": "get_account_balance", "arguments": {"account_id": "ACC-WS-001"}}, 3)
ws_log("CLIENT -> SERVER", call_req)
ws_log("SERVER -> CLIENT", server.handle(call_req))

for ts, direction, payload in conversation:
    print(f"[{ts}]  {direction}")
    print(_pretty(payload))
    print()
```

- A normal tool call, logged both ways, to show the conversation continues on the same connection.
- The final `for ts, direction, payload in conversation:` loop **unpacks** each recorded tuple back
  into its three parts and prints them as a neat timestamped transcript.

---

# Cell 22 — "Part B — Primitives" *(markdown)*

Section header with the five-primitives table (direction + who controls each). Nothing to run.

---

# Cell 23 — "B1 · Tools" *(markdown)*

Explains Tools (model-controlled actions, the "verbs"). Nothing to run.

---

# Cell 24 — Tools primitive demo *(code)*

**What it does:** discovers the tools, then calls both of them, printing every request and response.

```python
account_id = "ACC-JPM-2025"
principal, annual_rate, months = 500000, 8.5, 60
```

- The interactive knobs. The second line is **multiple assignment**: three names get three values
  in one line (`principal=500000`, `annual_rate=8.5`, `months=60`).

```python
list_req = jsonrpc_request("tools/list", {}, 1)
show_step("tools/list  REQUEST", list_req)
show_step("tools/list  RESPONSE", server.handle(list_req))
```

- Build a `tools/list` request, print it, then print what the server returns. This is **discovery**:
  "what tools do you have?"

```python
bal_req = jsonrpc_request("tools/call",
                          {"name": "get_account_balance", "arguments": {"account_id": account_id}}, 2)
bal_resp = server.handle(bal_req)
show_step("tools/call -> get_account_balance", bal_req)
show_step("tools/call <- result", bal_resp)
```

- Build a `tools/call` for `get_account_balance`, passing your `account_id`. `server.handle(...)`
  runs the stored lambda. We print both the request and the result.

```python
emi_req = jsonrpc_request("tools/call",
                          {"name": "calculate_emi",
                           "arguments": {"principal": principal, "annual_rate": annual_rate, "months": months}}, 3)
emi_resp = server.handle(emi_req)
show_step("tools/call -> calculate_emi", emi_req)
show_step("tools/call <- result", emi_resp)

print("RESULT:")
print(" ", bal_resp["result"]["content"][0]["text"])
print(" ", emi_resp["result"]["content"][0]["text"])
```

- Same pattern for the EMI tool, passing the three loan numbers.
- The final prints reach into each response — `["result"]["content"][0]["text"]` — to pull out just
  the human-readable answer.

---

# Cell 25 — "B2 · Resources" *(markdown)*

Explains Resources (app-controlled read-only data, the "nouns"). Nothing to run.

---

# Cell 26 — Resources primitive demo *(code)*

**What it does:** lists the resources, then reads one and prints its content.

```python
resource_uri = "bank://policies/kyc-rules"   # or "bank://customers/C001/profile"

list_req = jsonrpc_request("resources/list", {}, 1)
show_step("resources/list  REQUEST", list_req)
show_step("resources/list  RESPONSE", server.handle(list_req))

read_req = jsonrpc_request("resources/read", {"uri": resource_uri}, 2)
read_resp = server.handle(read_req)
show_step("resources/read  REQUEST", read_req)
show_step("resources/read  RESPONSE", read_resp)

content = read_resp["result"]["contents"][0]["text"]
print("RESOURCE CONTENT (this is injected into the AI's context):\n")
print(content)
```

- `resource_uri = "..."` — the knob; the comment reminds you of the other valid URI to try.
- The `resources/list` pair is the same discover-then-print rhythm as Tools.
- `read_req = jsonrpc_request("resources/read", {"uri": resource_uri}, 2)` — ask to read one
  specific resource by its URI.
- `content = read_resp["result"]["contents"][0]["text"]` — extract the text. (Note it's `contents`,
  plural, for resources — a small spelling difference from the tools path's `content`.)
- The demo prints the content, which is the data an application would feed into the model as
  context.

---

# Cell 27 — "B3 · Prompts" *(markdown)*

Explains Prompts (user-controlled reusable templates, like slash-commands). Nothing to run.

---

# Cell 28 — Prompts primitive demo *(code)*

**What it does:** lists the prompt templates, then fills one in with your arguments.

```python
prompt_name = "summarize_account_activity"
arguments = {"account_id": "ACC-JPM-2025", "days": "30"}

list_req = jsonrpc_request("prompts/list", {}, 1)
show_step("prompts/list  REQUEST", list_req)
show_step("prompts/list  RESPONSE", server.handle(list_req))

get_req = jsonrpc_request("prompts/get", {"name": prompt_name, "arguments": arguments}, 2)
get_resp = server.handle(get_req)
show_step("prompts/get  REQUEST", get_req)
show_step("prompts/get  RESPONSE", get_resp)

filled = get_resp["result"]["messages"][0]["content"]["text"]
print("FILLED PROMPT (ready to send to Claude):\n")
print(filled)
```

- `prompt_name` and `arguments` are the knobs. `arguments` is a dict whose keys **must match** the
  template's placeholders (`{account_id}`, `{days}`).
- `prompts/list` shows the available templates and the arguments each needs.
- `prompts/get` sends the chosen name plus arguments; back in Cell 8 the server does the
  `.replace(...)` filling and returns finished messages.
- `filled = get_resp["result"]["messages"][0]["content"]["text"]` — pull out the completed prompt
  text (`messages` → first item `[0]` → `content` → `text`). That text is now ready to send to a
  model.

---

# Cell 29 — "B4 · Sampling" *(markdown)*

Explains Sampling (the server borrows the *client's* AI — the reverse direction) with the
"contractor asks you to call your lawyer" analogy. Nothing to run.

---

# Cell 30 — Sampling primitive demo *(code)*

**What it does:** walks the four-step round-trip where the server asks the client's Claude to do
some reasoning. Uses real Claude if a key is set, otherwise a mock — so it always runs.

```python
text_to_summarize = (
    "The Model Context Protocol (MCP) standardises how AI applications connect to external tools "
    "and data sources. ..."
)
```

- The knob: the text the server will ask the client's AI to summarise. The parentheses let one
  string span several lines — Python joins the pieces into one string.

```python
call_req = jsonrpc_request("tools/call",
                           {"name": "get_account_balance", "arguments": {"account_id": "ACC-SAMPLE"}}, 1)
show_step("Step 1 - Client calls a tool", call_req)
```

- **Step 1** — a normal, left-to-right tool call, just to set the scene.

```python
sampling_request = {
    "jsonrpc": "2.0", "id": 99, "method": "sampling/createMessage",
    "params": {
        "messages": [{"role": "user", "content": {"type": "text",
                       "text": f"Please summarise the following in one sentence:\n\n{text_to_summarize}"}}],
        "maxTokens": 200,
        "systemPrompt": "You are a concise financial analyst. Summarise clearly.",
    },
}
show_step("Step 2 - Server asks the CLIENT's LLM (reverse direction!)", sampling_request)
```

- **Step 2** — the reversal. This is a request *the server sends back to the client*, asking it to
  run its LLM. `\n\n` inside the f-string means "two new lines" (a blank line) before the text.
  `maxTokens` caps the answer length; `systemPrompt` sets the AI's role.

```python
if anthropic_client and API_KEY:
    try:
        resp = anthropic_client.messages.create(
            model=MODEL, max_tokens=200,
            messages=[{"role": "user",
                       "content": f"Please summarise the following in one sentence:\n\n{text_to_summarize}"}],
        )
        ai_answer = resp.content[0].text
    except Exception as exc:
        ai_answer = f"[API call failed: {exc} - using mock] Summary of: '{text_to_summarize[:60]}...'"
else:
    ai_answer = f"[No API key - mock] The text explains MCP: '{text_to_summarize[:50]}...'"
```

- **Step 3** — the client fulfils the request.
- `if anthropic_client and API_KEY:` — only call real Claude if both a client and a key exist.
- `resp = anthropic_client.messages.create(...)` — the actual API call: it names the `model`, a
  length cap, and the `messages`. This is the one place in the notebook that reaches the internet.
- `ai_answer = resp.content[0].text` — read the model's reply out of the response object.
- `except Exception as exc:` — if the network call fails, fall back to a mock answer instead of
  crashing. `text_to_summarize[:60]` is a **slice**: the first 60 characters.
- `else:` — with no key, skip the API entirely and use a mock. This is why the notebook runs for
  everyone.

```python
sampling_response = jsonrpc_result(99, {
    "role": "assistant",
    "content": {"type": "text", "text": ai_answer},
    "model": MODEL, "stopReason": "end_turn",
})
show_step("Step 3 - Client returns Claude's answer to the server", sampling_response)

final_result = jsonrpc_result(1, {
    "content": [{"type": "text", "text": f"Summary (produced by client's Claude): {ai_answer}"}],
    "isError": False,
})
show_step("Step 4 - Server returns the final tool result", final_result)

print("AI SUMMARY:\n", ai_answer)
```

- The client packages `ai_answer` as a JSON-RPC response (id `99`, matching the sampling request)
  and sends it back to the server.
- **Step 4** — the server uses that AI answer to finish the *original* tool call (id `1`).
- The final `print` shows the summary text on its own.

> 🐍 **New idea — the reverse round-trip.** Follow the ids: the server's request is id `99`; the
> client's reply is id `99`; the original tool call is id `1`. Matching ids is how JSON-RPC keeps
> replies paired with their requests, even when calls are nested.

---

# Cell 31 — "B5 · Roots" *(markdown)*

Explains Roots (the client declares which folders/URLs the server may touch) with the "keys to
specific rooms" analogy. Nothing to run.

---

# Cell 32 — Roots primitive demo *(code)*

**What it does:** the client declares allowed locations, the server asks for them, and we show an
allowed path versus a denied one.

```python
root1 = "file:///home/user/project"
root2 = "file:///home/user/shared"

declared_roots = [r.strip() for r in [root1, root2] if r.strip()]
server._roots = [{"uri": r, "name": r.split("/")[-1] or r} for r in declared_roots]
```

- `root1`, `root2` — the knobs: the folders the client is willing to grant.
- `declared_roots = [r.strip() for r in [root1, root2] if r.strip()]` — a list comprehension **with
  a filter.** It walks `[root1, root2]`, calls `.strip()` to trim whitespace, and the trailing
  `if r.strip()` keeps only non-empty entries. So blank inputs are dropped.
- `server._roots = [{"uri": r, "name": r.split("/")[-1] or r} for r in declared_roots]` — build the
  list of root objects the server will report. `r.split("/")` breaks the URI on every `/`; `[-1]`
  takes the **last** piece (the folder name, e.g. `project`). The `or r` is a fallback: if that last
  piece is empty, use the whole URI as the name.

```python
roots_req = jsonrpc_request("roots/list", {}, 1)
show_step("Server asks the client: roots/list", roots_req)
show_step("Client answers with its declared roots", server.handle(roots_req))
```

- The server asks "what am I allowed to touch?" via `roots/list`, and the client answers with the
  roots we just set. Direction note: here the *server* is asking the *client*.

```python
allowed = declared_roots[0] if declared_roots else "none"
show_step("Server checks a path INSIDE its roots", {
    "server_attempted_to_access": f"{allowed}/transactions/2025.csv",
    "is_within_roots": True,
    "action": "ALLOWED - path is inside a declared root",
})

show_step("Server checks a path OUTSIDE its roots", {
    "server_attempted_to_access": "/etc/passwords",
    "is_within_roots": False,
    "action": "DENIED - path is NOT in any declared root",
})
```

- `allowed = declared_roots[0] if declared_roots else "none"` — a ternary: use the first granted
  root if there is one, otherwise the word `"none"`. `[0]` is the first item of a list.
- The two `show_step` calls illustrate the security rule: a file *inside* a granted root is allowed;
  `/etc/passwords`, outside every root, is denied. (These are illustrative dictionaries, not a real
  filesystem check.)

```python
print("Roots granted to the server:")
for r in declared_roots:
    print("  [OK]", r)
print("\nCapability lives on the server. Authority lives on the client.")
```

- A `for` loop prints each granted root on its own line, followed by the one-sentence takeaway.

---

# Cell 33 — Cheat sheet & recap *(markdown)*

The one-page summary: both comparison tables, the banking examples, the golden rule, a pointer to
the companion SDK notebook, and a homework task. Nothing to run — it's your revision card.

---

## The five things to leave the class with

1. **Every message is JSON-RPC 2.0.** A request has `method` + `params`; a response has `result` or
   `error`; the `id` pairs them up. That never changes.
2. **`server.handle(request)` is the whole server.** One method reads `method` and returns the right
   response. Read it once and MCP stops being mysterious.
3. **Transport ≠ primitive.** Transport is the pipe (stdio/HTTP/WebSocket); the primitive is the
   cargo (Tools/Resources/Prompts/Sampling/Roots). The cargo is identical across pipes.
4. **Who's in control differs per primitive.** Tools → the model; Resources → the app; Prompts →
   the user; Sampling → the server borrows the client's AI; Roots → the client sets the fence.
5. **The Python patterns repeat.** Build a dict → hand it to `server.handle` → read the nested
   result → print it. Once you see that loop, every demo cell is the same shape with a different
   `method`.

*Tip for teaching: run each code cell, then change one "knob" variable at the top and re-run, so
learners see the request and response move together.*
