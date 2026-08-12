# MCP Server Patterns — Line-by-Line Guide

### A beginner's companion to `mcp_server_patterns_demo.ipynb` | Teal Trust Workshop

This guide walks through **every cell** of the notebook and explains **each line** — every
function, class, method, decorator, and Python trick — in plain language, for someone new to
Python. Read a cell in the notebook, then read the matching section here.

This notebook is larger than the earlier MCP Explorer one, and it introduces a few new Python
ideas (decorators, subprocesses, SQLite, an agent loop). Don't worry — every new idea is explained
the first time it appears, with a **🐍 New idea** callout.

> **What the notebook actually does at runtime:** it *writes real MCP server programs to disk*
> (into an `mcp_servers/` folder), *launches them as separate processes*, and *talks to them over
> JSON-RPC 2.0*. So a few cells create files (`_mcp_base.py`, `general_server.py`, `math_server.py`,
> `banking_server.py`, `stateful_server.py`) and one creates a small database (`banking.db`). That's
> expected and safe.

---

## Part 0 — Python building blocks you'll meet

Skim these now; refer back whenever a symbol looks unfamiliar. The first ten also appeared in the
MCP Explorer guide; the rest are new in this notebook.

**1. Variable & `print`.** `x = 5` stores a value; `print(x)` shows it.

**2. f-string.** `f"Hi {name}"` drops a value into text.

**3. Dictionary.** `{"key": value}` — a labelled bag. `d["key"]` looks up; `d.get("key", default)`
looks up safely (returns `default` if missing instead of crashing).

**4. List.** `[a, b, c]` — an ordered sequence. `mylist[-1]` is the last item.

**5. List comprehension.** `[f(x) for x in items]` builds a new list in one line. Add a filter:
`[x for x in items if keep(x)]`.

**6. `lambda`.** A one-line unnamed function: `square = lambda x: x*x`.

**7. `def` / `class` / `self`.** `def` makes a named function; `class` a blueprint for objects;
`self` means "this object" inside a class.

**8. `try` / `except`.** Attempt something; if it fails, run the fallback instead of crashing.

**9. `**kwargs` unpacking.** A dict spreads into keyword arguments: `f(**{"a": 1})` is `f(a=1)`.

**10. Ternary & `or`-default.** `A if cond else B` is a one-line if/else. `a or b` gives `a` unless
it's empty/None, then `b`.

**— New in this notebook —**

**11. Decorator (`@something`).** A decorator is a function that takes your function and does
something with it — here, *registers* it. Reading `@srv.tool(...)` above a `def` as: "*this function
is a tool.*" Full explanation in Cell 6.

**12. `@property`.** Lets you call a method like a plain attribute — `client.pid` with no
parentheses. Explained in Cell 8.

**13. Subprocess.** `subprocess.Popen([...])` launches *another program*. You send it text through a
**pipe** (stdin) and read its replies from another pipe (stdout). Explained in Cell 8.

**14. `global`.** Inside a function, `global x` says "use the module-level `x`, don't make a new
local one." Used for lazy one-time setup. Explained in Cell 22.

**15. SQLite.** A tiny built-in database. `sqlite3.connect(file)` opens it; `conn.execute(sql, args)`
runs a query; `?` placeholders safely insert values. Explained in Cell 17.

**16. `json.dumps` / `json.loads`.** `dumps` turns a Python object into JSON *text*; `loads` parses
JSON text back into a Python object. This is how messages cross the pipe.

---

## The MCP idea in one paragraph

Everything here rides on **JSON-RPC 2.0**: a *client* sends a **request**
(`{"method": ..., "params": ...}`) and a *server* replies with a **response**
(`{"result": ...}` or `{"error": ...}`). MCP defines three **primitives** the request can be about —
**tools** (actions), **resources** (read-only data), **prompts** (templates) — plus two advanced
moves, **sampling** (the server borrows the client's AI) and **stateless vs stateful** servers. The
whole notebook is: build a request → send it over a pipe → read the response → print it.

---

# Cell 1 — Title & big picture *(markdown)*

Introduces the project, the "N×M → N+M" idea (write a tool once as a server, any agent can use it),
the architecture diagram, and a table of what we'll build. Nothing to run.

---

# Cell 2 — "Setup" heading *(markdown)*

Explains we need only the standard library plus optional `python-dotenv` and `anthropic`, and that
we'll create an `mcp_servers/` folder. Nothing to run.

---

# Cell 3 — Setup: imports, folders, API key *(code)*

**What it does:** imports the toolkits, optionally loads `.env`, finds the API key (without
quitting if missing), picks a model, and creates the `mcp_servers/` folder.

```python
import os, sys, json, time, subprocess, threading, sqlite3, textwrap

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    import anthropic
except Exception:
    anthropic = None

API_KEY = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY", "")
MODEL   = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

ROOT = os.getcwd()
SERVERS = os.path.join(ROOT, "mcp_servers")
os.makedirs(SERVERS, exist_ok=True)

def have_key():
    return bool(API_KEY) and anthropic is not None

print("Working dir :", ROOT)
print("Servers dir :", SERVERS)
if have_key():
    print(f"API key found -> agentic patterns will call real Claude ({MODEL}).")
else:
    print("No API key (or anthropic not installed) -> agentic patterns fall back to direct tool calls.")
    print("The MCP mechanics still run fully.")
```

- `import os, sys, json, time, subprocess, threading, sqlite3, textwrap` — load eight standard-library
  toolkits on one line: `os` (files/paths/env), `sys` (this Python's path), `json` (the wire format),
  `time` (uptime), `subprocess` (launch server programs), `threading` (a safety lock), `sqlite3`
  (the banking database), `textwrap` (tidy text).
- `try: from dotenv import load_dotenv / load_dotenv()` — if the optional `python-dotenv` package is
  installed, read a `.env` file into the environment. `except Exception: pass` = if it's not
  installed, do nothing.
- `try: import anthropic / except Exception: anthropic = None` — try to load the Anthropic SDK. If
  it isn't installed, set the name `anthropic` to `None` so later code can check for it instead of
  crashing.
- `API_KEY = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY", "")` — read the
  key. `os.environ.get("NAME")` returns the value or `None`; the **`or`** tries the second name if
  the first is empty; the `""` is a final default so `API_KEY` is never `None`.
- `MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")` — read a model name, defaulting to
  Sonnet if not set.
- `ROOT = os.getcwd()` — "get current working directory": the folder the notebook runs in.
- `SERVERS = os.path.join(ROOT, "mcp_servers")` — build the path `ROOT/mcp_servers`. `os.path.join`
  glues path pieces with the correct separator for your OS.
- `os.makedirs(SERVERS, exist_ok=True)` — create that folder. `exist_ok=True` means "don't error if
  it already exists."
- `def have_key(): return bool(API_KEY) and anthropic is not None` — a helper answering "can we call
  real Claude?" `bool(API_KEY)` is `True` only if the key string is non-empty; `and` requires the SDK
  to be present too. We call this all over the notebook to decide real-Claude vs fallback.
- The `print(...)` lines report the folders and whether Claude is available.

> 🐍 **New idea — graceful optional dependencies.** Wrapping imports in `try/except` and storing
> `None` on failure lets the notebook run even when an optional package or key is missing. That's why
> every cell works in class regardless of setup.

---

# Cell 4 — "The MCP wire contract" *(markdown)*

A recap table of the seven JSON-RPC methods a client uses (`initialize`, `tools/list`, `tools/call`,
`resources/list`, `resources/read`, `prompts/list`, `prompts/get`). Nothing to run.

---

# Cell 5 — "Part 1 · The server framework" *(markdown)*

Explains that every server reuses a tiny base class with decorators and one `handle()` method.
Nothing to run — it sets up the next cell.

---

# Cell 6 — Write `_mcp_base.py` (the framework) *(code)*

**What it does:** stores the framework's source as text, writes it to `mcp_servers/_mcp_base.py`,
and prints it. This cell has two layers: the small **wrapper** that saves the file, and the
**server framework code** inside the string.

### The wrapper (top and bottom of the cell)

```python
server_src = r"""
# _mcp_base.py  --  minimal MCP server framework ...
...
"""

with open(os.path.join(SERVERS, "_mcp_base.py"), "w") as f:
    f.write(server_src)
print("Wrote mcp_servers/_mcp_base.py  (" + str(server_src.count(chr(10))) + " lines)")
print(server_src)
```

- `server_src = r"""..."""` — a **raw, triple-quoted string** holding an entire program as text.
  Triple quotes let it span many lines. The `r` (raw) keeps backslashes literal, so a `"\n"` written
  inside the framework stays as the two characters `\` `n` in the file (Python will interpret it as a
  newline only when the *server* runs).
- `with open(..., "w") as f:` — open the destination file for **w**riting; the `with` block closes it
  automatically afterwards.
- `f.write(server_src)` — write the program text into the file.
- `server_src.count(chr(10))` — count newline characters (`chr(10)` *is* the newline character), i.e.
  how many lines the file has.
- `print(server_src)` — show the source so students can read it.

### The framework code (inside the string) — the important part

```python
import sys, json

class MCPServer:
    def __init__(self, name, version="1.0.0"):
        self.name = name
        self.version = version
        self._tools = {}       # name -> {description, inputSchema, fn}
        self._resources = {}   # uri  -> {description, fn}
        self._prompts = {}     # name -> {description, arguments, fn}
```

- `class MCPServer:` — the blueprint every server builds on.
- `__init__` — the constructor. It stores the server's `name`/`version` and starts three empty
  dictionaries to hold whatever tools, resources, and prompts get registered.

```python
    def tool(self, name, description, input_schema):
        def deco(fn):
            self._tools[name] = {"description": description, "inputSchema": input_schema, "fn": fn}
            return fn
        return deco
```

- This is a **decorator factory**. When a server writes `@srv.tool("convert_units", "...", {...})`
  above a function, here's what happens step by step:
  1. Python calls `srv.tool("convert_units", ...)`. That runs the method above, which *defines* an
     inner function `deco` and returns it.
  2. Python then calls `deco(convert_units)` — passing the just-defined function in as `fn`.
  3. Inside `deco`, the line `self._tools[name] = {..., "fn": fn}` **saves the function** in the
     server's tools dictionary under its name, along with its description and input schema.
  4. `return fn` hands the function back unchanged, so it still works normally.
- Net effect: the `@srv.tool(...)` line means "register this function as a tool named …". `resource`
  and `prompt` below follow the exact same shape.

```python
    def resource(self, uri, description):
        def deco(fn):
            self._resources[uri] = {"description": description, "fn": fn}
            return fn
        return deco

    def prompt(self, name, description, arguments):
        def deco(fn):
            self._prompts[name] = {"description": description, "arguments": arguments, "fn": fn}
            return fn
        return deco
```

- Same decorator pattern: `resource` stores a function under a URI; `prompt` stores one under a name
  plus the list of argument names it expects.

```python
    def _ok(self, rid, result):
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    def _err(self, rid, code, message):
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}
```

- Two tiny helpers that build a success response (`_ok`) or an error response (`_err`) in proper
  JSON-RPC shape. `rid` is the request id echoed back so the client can match reply to request.

```python
    def handle(self, req):
        method = req.get("method")
        rid = req.get("id")
        params = req.get("params") or {}

        if method == "initialize":
            return self._ok(rid, {
                "protocolVersion": "2025-06-18",
                "serverInfo": {"name": self.name, "version": self.version},
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}}})
```

- `handle(self, req)` — **the whole protocol lives here.** You hand it a request dict; it returns a
  response dict. Read `method`, `id`, and `params` out of the request (`params or {}` guards against
  a missing/None params).
- The first branch answers the handshake (`initialize`) with the server's identity and capabilities.

```python
        if method == "tools/list":
            return self._ok(rid, {"tools": [
                {"name": n, "description": d["description"], "inputSchema": d["inputSchema"]}
                for n, d in self._tools.items()]})
```

- For `tools/list`, a **list comprehension** walks the tools dict (`.items()` gives each name `n` and
  detail `d`) and builds a public list of `{name, description, inputSchema}` — deliberately leaving
  out the private `fn`.

```python
        if method == "tools/call":
            name = params.get("name"); args = params.get("arguments") or {}
            if name not in self._tools:
                return self._err(rid, -32601, "tool not found: " + str(name))
            try:
                text = self._tools[name]["fn"](**args)
                return self._ok(rid, {"content": [{"type": "text", "text": str(text)}], "isError": False})
            except Exception as e:
                return self._ok(rid, {"content": [{"type": "text", "text": "error: " + str(e)}], "isError": True})
```

- For `tools/call`: read which tool and its arguments. If unknown → error `-32601` (the standard
  "method not found" code).
- `text = self._tools[name]["fn"](**args)` — the key line: fetch the stored function and **call it**,
  unpacking the args dict into keyword arguments (`**args`). If `args` is `{"symbol": "INFY"}`, this
  runs `fn(symbol="INFY")`.
- Wrap success as text content with `isError: False`. If the tool throws, `except` catches it and
  returns the error text with `isError: True` — so one bad call never crashes the server.

```python
        if method == "resources/list":
            return self._ok(rid, {"resources": [
                {"uri": u, "description": d["description"]} for u, d in self._resources.items()]})

        if method == "resources/read":
            uri = params.get("uri")
            if uri not in self._resources:
                return self._err(rid, -32601, "resource not found: " + str(uri))
            text = self._resources[uri]["fn"]()
            return self._ok(rid, {"contents": [{"uri": uri, "mimeType": "text/plain", "text": str(text)}]})
```

- `resources/list` mirrors `tools/list`. `resources/read` looks up the URI, calls its function
  (`fn()` — resources take no arguments), and returns the text under `contents`.

```python
        if method == "prompts/list":
            return self._ok(rid, {"prompts": [
                {"name": n, "description": d["description"],
                 "arguments": [{"name": a, "required": True} for a in d["arguments"]]}
                for n, d in self._prompts.items()]})

        if method == "prompts/get":
            name = params.get("name"); args = params.get("arguments") or {}
            if name not in self._prompts:
                return self._err(rid, -32601, "prompt not found: " + str(name))
            text = self._prompts[name]["fn"](**args)
            return self._ok(rid, {"messages": [
                {"role": "user", "content": {"type": "text", "text": str(text)}}]})

        return self._err(rid, -32601, "unknown method: " + str(method))
```

- `prompts/list` uses a **comprehension inside a comprehension** (the inner one turns each argument
  name into a `{name, required}` entry).
- `prompts/get` calls the prompt's function with the supplied arguments (`**args`) to *render* the
  template, and returns it as a ready-to-send chat message.
- The final `return self._err(...)` catches any method the server doesn't know.

```python
    def serve_forever(self):
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except Exception:
                continue
            sys.stdout.write(json.dumps(self.handle(req)) + "\n")
            sys.stdout.flush()
```

- `serve_forever` is the server's main loop. `for line in sys.stdin:` reads requests **one line at a
  time** from standard input (the pipe the client writes to), waiting when there's nothing.
- `line.strip()` trims whitespace; `if not line: continue` skips blank lines.
- `req = json.loads(line)` parses the JSON text into a dict (guarded by `try` so a malformed line is
  skipped).
- `sys.stdout.write(json.dumps(self.handle(req)) + "\n")` — process the request, turn the response
  back into JSON text, add a newline, and send it out.
- `sys.stdout.flush()` — push it out **now**; without flushing, the reply can get stuck in a buffer
  and the client waits forever.

> 🐍 **New idea — decorator.** `@srv.tool(...)` doesn't change what your function *does*; it just
> **registers** it with the server so `tools/call` can find and run it later. It's the notebook's
> single most important Python idea — everything a server exposes is registered this way.

---

# Cell 7 — "Part 2 · The MCP client" *(markdown)*

Explains that the client spawns a server as a subprocess, speaks JSON-RPC over its stdin/stdout, and
records every message so we can print the wire trace. Nothing to run.

---

# Cell 8 — The `MCPClient` class *(code)*

**What it does:** defines the client object that launches a server program and exchanges JSON-RPC
messages with it.

### Constructor and lifecycle

```python
class MCPClient:
    def __init__(self, server_path, env_extra=None, name=None):
        self.server_path = server_path
        self.name = name or os.path.basename(server_path)
        self.env_extra = env_extra or {}
        self.proc = None
        self._id = 0
        self._lock = threading.Lock()
        self.trace = []
        self.started_at = None
```

- `__init__` stores where the server file is (`server_path`), a friendly `name` (defaulting to the
  filename via `os.path.basename`), and any extra environment variables (`env_extra`).
- `self.proc = None` — will hold the running subprocess later.
- `self._id = 0` — a counter for request ids (each request gets the next number).
- `self._lock = threading.Lock()` — a "one at a time" gate (see below).
- `self.trace = []` — the list that records every message for the wire display.
- `self.started_at = None` — will hold the start time for uptime.

```python
    def start(self):
        env = dict(os.environ); env.update(self.env_extra)
        self.proc = subprocess.Popen(
            [sys.executable, self.server_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1, env=env)
        self.started_at = time.time()
        self._request("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "demo-client", "version": "1.0"}})
        return self
```

- `env = dict(os.environ); env.update(self.env_extra)` — copy the current environment variables and
  add any extras (used later to pass `MCP_MODE` or `BANKING_DB` to a server).
- `subprocess.Popen([...], ...)` — **launch the server program.** `[sys.executable, self.server_path]`
  is the command line: "run this Python on that server file."
  - `stdin=PIPE` / `stdout=PIPE` — create pipes to write to and read from the child.
  - `stderr=PIPE` — capture its error stream.
  - `text=True` — exchange normal strings, not raw bytes.
  - `bufsize=1` — line-buffered, so lines flush promptly.
  - `env=env` — hand the child our environment (plus extras).
- `self.started_at = time.time()` — record the start time (seconds since 1970).
- `self._request("initialize", {...})` — immediately do the handshake so the server is ready.
- `return self` — hand the started client back, which lets you write `MCPClient(...).start()` in one
  line.

```python
    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try: self.proc.wait(timeout=3)
            except Exception: self.proc.kill()

    def is_alive(self):
        return self.proc is not None and self.proc.poll() is None
```

- `stop` shuts the server down. `self.proc.poll()` returns `None` while the child is still running (a
  number once it's exited), so `poll() is None` means "still alive." `terminate()` asks it to stop;
  if it doesn't within 3 seconds, `kill()` forces it.
- `is_alive` returns `True` only if a process exists and is still running.

```python
    @property
    def pid(self):
        return self.proc.pid if self.proc else None

    @property
    def uptime(self):
        return round(time.time() - self.started_at, 1) if self.started_at else 0
```

- `@property` turns these methods into **read-only attributes**: you write `client.pid` and
  `client.uptime` with **no parentheses**, and Python runs the method behind the scenes. `pid` is the
  OS process id; `uptime` is "now minus start time," rounded to one decimal.

### One JSON-RPC round-trip

```python
    def _request(self, method, params=None, timeout=15):
        with self._lock:
            self._id += 1
            req = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}
            self.trace.append({"dir": "->", "msg": req})
            try:
                self.proc.stdin.write(json.dumps(req) + "\n")
                self.proc.stdin.flush()
                line = self.proc.stdout.readline()
                if not line:
                    err = {"error": "no response (server may have crashed)"}
                    self.trace.append({"dir": "<-", "msg": err}); return err
                resp = json.loads(line.strip())
                self.trace.append({"dir": "<-", "msg": resp}); return resp
            except Exception as e:
                err = {"error": f"transport error: {e}"}
                self.trace.append({"dir": "<-", "msg": err}); return err
```

- `with self._lock:` — enter the "one at a time" gate. Only one call can be inside at once, so two
  overlapping requests can't scramble each other's messages on the shared pipe.
- `self._id += 1` — bump the id counter.
- `req = {...}` — build the JSON-RPC request.
- `self.trace.append({"dir": "->", "msg": req})` — record it as an outgoing message (`->`).
- `self.proc.stdin.write(json.dumps(req) + "\n")` then `.flush()` — send the request as one JSON
  line and push it through.
- `line = self.proc.stdout.readline()` — **wait for and read one line** of the server's reply.
- `if not line:` — an empty read means the server produced nothing (likely crashed); record and
  return an error.
- `resp = json.loads(line.strip())` — parse the reply text into a dict, record it as incoming
  (`<-`), and return it.
- `except Exception as e:` — any pipe/parse failure is captured as an error instead of crashing.

### The primitive wrappers

```python
    def list_tools(self):
        return self._request("tools/list").get("result", {}).get("tools", [])

    def call_tool(self, name, arguments):
        r = self._request("tools/call", {"name": name, "arguments": arguments})
        if "error" in r:
            return json.dumps(r["error"])
        return "\n".join(c.get("text", "") for c in r.get("result", {}).get("content", []))
```

- `list_tools` sends `tools/list` and digs the tool list out of the response. The chain
  `.get("result", {}).get("tools", [])` reads `result.tools` **safely** — if either key is missing it
  falls back to `{}` or `[]` instead of crashing.
- `call_tool` sends `tools/call`. If the response has an `error`, return it as text. Otherwise, join
  the `text` fields of every content block. The `"\n".join(... for ...)` is a **generator expression**
  fed to `join`: it produces each text piece and glues them with newlines.

```python
    def list_resources(self):
        return self._request("resources/list").get("result", {}).get("resources", [])

    def read_resource(self, uri):
        r = self._request("resources/read", {"uri": uri})
        return "\n".join(c.get("text", "") for c in r.get("result", {}).get("contents", []))

    def list_prompts(self):
        return self._request("prompts/list").get("result", {}).get("prompts", [])

    def get_prompt(self, name, arguments):
        r = self._request("prompts/get", {"name": name, "arguments": arguments})
        return "\n".join(m.get("content", {}).get("text", "")
                         for m in r.get("result", {}).get("messages", []))

    def clear_trace(self):
        self.trace = []
```

- The resource and prompt wrappers follow the same pattern: send the request, then safely extract the
  text. `get_prompt` reaches into each rendered message's `content.text`.
- `clear_trace` empties the recorded messages, so each demo starts with a clean wire log.

> 🐍 **New idea — subprocess pipes.** The client and server are **two separate programs**. The
> client writes a JSON line into the server's input pipe and reads a JSON line from its output pipe —
> exactly how real MCP tools (like Claude Desktop) talk to local servers.

---

# Cell 9 — "Small helpers to view results" *(markdown)*

Introduces three print helpers. Nothing to run.

---

# Cell 10 — Print helpers *(code)*

**What it does:** defines functions that pretty-print the wire trace, the agent's steps, and the
final answer.

```python
def print_trace(client, last=20):
    print("\n----- MCP wire trace (JSON-RPC 2.0) -----")
    if not client or not client.trace:
        print("(no messages yet)"); return
    for e in client.trace[-last:]:
        arrow = "CLIENT --> SERVER" if e["dir"] == "->" else "SERVER --> CLIENT"
        print(arrow)
        print(json.dumps(e["msg"], indent=2))
        print()
```

- `print_trace(client, last=20)` — show the last `last` recorded messages (default 20).
- `if not client or not client.trace:` — if there's no client or nothing recorded, say so and
  `return` early.
- `for e in client.trace[-last:]:` — loop over the last messages. `[-last:]` is a **slice** meaning
  "the final `last` items."
- `arrow = "..." if e["dir"] == "->" else "..."` — a ternary that labels the direction.
- `json.dumps(e["msg"], indent=2)` — pretty-print the message with 2-space indentation.

```python
def print_log(log):
    icon = {"thought": "THINK", "action": "ACT", "observation": "OBSERVE", "info": "INFO"}
    print("\n----- ReAct steps -----")
    for kind, content in log:
        c = content
        if kind == "observation" and len(str(c)) > 400:
            c = str(c)[:400] + " ...(truncated)"
        print(f"[{icon.get(kind, kind.upper())}] {c}")
```

- `print_log(log)` — print the agent's reasoning steps. `log` is a list of `(kind, content)` pairs.
- `icon = {...}` maps each step kind to a short label.
- `for kind, content in log:` — **unpack** each pair into `kind` and `content`.
- The `if ... len(str(c)) > 400:` line trims very long observations so the output stays readable.
  `str(c)[:400]` is the first 400 characters.
- `icon.get(kind, kind.upper())` — look up the label, or fall back to the uppercased kind.

```python
def print_answer(r):
    print("ANSWER:\n" + str(r.get("answer", "")))
    u = r.get("usage") or {}
    if u:
        print(f"\n[tokens in/out: {u.get('input_tokens',0)}/{u.get('output_tokens',0)}"
              f"  est. cost ~${r.get('cost_usd',0):.5f}]")

print("Print helpers ready.")
```

- `print_answer(r)` — print the final answer, then (if usage info exists) the token counts and
  estimated cost. `r.get("usage") or {}` guards against missing usage. `:.5f` formats the cost to 5
  decimals.

---

# Cell 11 — "Part 3 · Write the four MCP servers" *(markdown)*

Says the next four cells write real server programs into `mcp_servers/`. Nothing to run.

---

# Cell 12 — "3a · general_server.py" *(markdown)*

Describes the general server's two tools, two resources, and one prompt. Nothing to run.

---

# Cell 13 — Write `general_server.py` *(code)*

**What it does:** writes the general server to disk and prints it. The **wrapper** (create the string,
`open(...).write`, print) is identical to Cell 6 — see that explanation. Here we focus on the
**server code inside the string**.

```python
from _mcp_base import MCPServer

srv = MCPServer("general-server")

LEN = {"m": 1.0, "km": 1000.0, "mile": 1609.344, "miles": 1609.344, "ft": 0.3048, "feet": 0.3048}
```

- `from _mcp_base import MCPServer` — import the framework we wrote in Cell 6. (This works because the
  client launches the server *from inside* `mcp_servers/`, so `_mcp_base.py` sits right next to it.)
- `srv = MCPServer("general-server")` — create this server object.
- `LEN = {...}` — a lookup table of how many **metres** each length unit is worth. This is the trick
  that makes conversion simple: convert everything to metres, then to the target unit.

```python
@srv.tool("convert_units", "Convert a length between units (m, km, mile, ft).",
          {"type": "object",
           "properties": {"value": {"type": "number"},
                          "from_unit": {"type": "string"},
                          "to_unit": {"type": "string"}},
           "required": ["value", "from_unit", "to_unit"]})
def convert_units(value, from_unit, to_unit):
    fu, tu = str(from_unit).lower(), str(to_unit).lower()
    if fu not in LEN or tu not in LEN:
        return "unsupported unit(s): " + str(from_unit) + ", " + str(to_unit)
    meters = float(value) * LEN[fu]
    result = meters / LEN[tu]
    return str(value) + " " + from_unit + " = " + format(result, ".4f") + " " + to_unit
```

- The `@srv.tool(...)` decorator (from Cell 6) **registers** this function as a tool. Its three
  arguments are the tool's name, description, and **input schema** — a dict declaring the tool takes
  three inputs (`value`, `from_unit`, `to_unit`), all required. Claude reads this schema to know how
  to call the tool.
- `fu, tu = str(from_unit).lower(), str(to_unit).lower()` — lowercase both unit names so "KM" and
  "km" both work. This is **multiple assignment** (two names, two values).
- `if fu not in LEN or tu not in LEN:` — if either unit is unknown, return a friendly message.
- `meters = float(value) * LEN[fu]` — convert the input to metres. `float(value)` makes sure it's a
  number.
- `result = meters / LEN[tu]` — convert metres to the target unit.
- The `return` builds the answer text. `format(result, ".4f")` shows 4 decimal places.

```python
@srv.tool("get_stock_quote", "Return a (mock) delayed stock quote for a ticker symbol.",
          {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]})
def get_stock_quote(symbol):
    price = 500 + (abs(hash(str(symbol).upper())) % 2000)
    return str(symbol).upper() + ": INR " + format(price, ",") + ".00 (mock delayed quote)"
```

- A second tool. `hash(...)` turns the symbol text into a number; `abs(...)` makes it positive;
  `% 2000` keeps it in 0–1999; `+ 500` shifts it to 500–2499 — a believable *fake* price. `format(price, ",")`
  adds thousands separators. It's a mock (no real market data), which is why prices may differ between
  sessions.

```python
@srv.resource("policy://kyc-summary", "One-paragraph KYC policy summary.")
def kyc_summary():
    return ("KYC policy: government photo ID + address proof are mandatory. "
            "PAN required for transactions above INR 50,000. Re-verify every 24 months.")

@srv.resource("customer://C-1001", "Static profile card for customer C-1001.")
def customer_c1001():
    return "C-1001 | Arjun Mehta | premium/current | Mumbai | KYC verified"
```

- Two **resources** — read-only data behind URIs. Note resource functions take **no arguments** and
  just return text. The framework's `resources/read` calls them with `fn()`.

```python
@srv.prompt("structured_analysis", "Template: structured analysis of a topic for an audience.",
            ["topic", "audience"])
def structured_analysis(topic, audience="a general audience"):
    return ("Give a structured analysis of " + str(topic) + " for " + str(audience) + ". "
            "Use three sections: (1) what it is, (2) why it matters, (3) key trade-offs. "
            "Keep each section to 3 bullet points.")

srv.serve_forever()
```

- A **prompt** template. Its argument list is `["topic", "audience"]`. The function fills those into
  a reusable instruction. `audience="a general audience"` is a default, so `audience` is optional.
- `srv.serve_forever()` — the last line **starts the server loop** (from Cell 6). When the client
  launches this file, execution reaches here and the server waits for requests.

> 🐍 **New idea — a JSON Schema for a tool.** The dict you pass to `@srv.tool(...)` isn't decoration —
> it's the *contract* the model reads to decide how to call the tool. `"required": [...]` tells the
> model which arguments it must supply.

---

# Cell 14 — "3b · math_server.py" *(markdown)*

Describes the second server (tools only), whose purpose is to exist as a separate server for
fan-out. Nothing to run.

---

# Cell 15 — Write `math_server.py` *(code)*

Same wrapper as before; the server inside registers two tools.

```python
from _mcp_base import MCPServer
srv = MCPServer("math-server")

@srv.tool("compound_interest", "Compound interest: final amount and interest for P at rate% for years.",
          {"type": "object",
           "properties": {"principal": {"type": "number"}, "rate": {"type": "number"},
                          "years": {"type": "number"}, "compounds_per_year": {"type": "integer"}},
           "required": ["principal", "rate", "years"]})
def compound_interest(principal, rate, years, compounds_per_year=1):
    P = float(principal); r = float(rate) / 100.0; n = int(compounds_per_year); t = float(years)
    amount = P * (1 + r / n) ** (n * t)
    interest = amount - P
    return ("Compound interest on " + format(P, ",.0f") + " at " + str(rate) + "% for "
            + str(years) + "y (n=" + str(n) + "): amount = " + format(amount, ",.2f")
            + ", interest = " + format(interest, ",.2f"))
```

- `compound_interest` takes principal, rate, years, and an optional `compounds_per_year` (default 1).
- `r = float(rate) / 100.0` — convert a percentage (e.g. 8) into a fraction (0.08).
- `amount = P * (1 + r / n) ** (n * t)` — the compound-interest formula. `**` is "to the power of."
- `interest = amount - P` — how much was earned.
- `format(x, ",.2f")` shows thousands separators and 2 decimals; `",.0f"` shows 0 decimals.

```python
@srv.tool("simple_interest", "Simple interest for P at rate% for years.",
          {"type": "object",
           "properties": {"principal": {"type": "number"}, "rate": {"type": "number"},
                          "years": {"type": "number"}},
           "required": ["principal", "rate", "years"]})
def simple_interest(principal, rate, years):
    P = float(principal); interest = P * float(rate) / 100.0 * float(years)
    return "Simple interest = " + format(interest, ",.2f") + " (on principal " + format(P, ",.0f") + ")"

srv.serve_forever()
```

- `simple_interest` uses the plain formula `P × rate% × years`. Then `serve_forever()` starts it.

---

# Cell 16 — "3c · Seed the banking DB, then banking_server.py" *(markdown)*

Explains we first seed a small SQLite database, then write the server that reads it. Nothing to run.

---

# Cell 17 — Seed `banking.db` *(code)*

**What it does:** creates a fresh SQLite database with two tables and some rows.

```python
BANKING_DB = os.path.join(ROOT, "banking.db")
if os.path.exists(BANKING_DB):
    os.remove(BANKING_DB)
conn = sqlite3.connect(BANKING_DB); c = conn.cursor()
c.executescript("""
CREATE TABLE accounts (
    customer_id TEXT PRIMARY KEY, name TEXT, segment TEXT,
    account_type TEXT, balance REAL, city TEXT, kyc_status TEXT);
CREATE TABLE transactions (
    txn_id INTEGER PRIMARY KEY, customer_id TEXT, txn_date TEXT,
    type TEXT, amount REAL, description TEXT);
""")
```

- `BANKING_DB = os.path.join(ROOT, "banking.db")` — the database file path.
- `if os.path.exists(BANKING_DB): os.remove(BANKING_DB)` — delete any old copy so we start fresh.
- `conn = sqlite3.connect(BANKING_DB)` — open (creating) the database file. `c = conn.cursor()` gets
  a cursor, the object you run SQL through.
- `c.executescript("""...""")` — run several SQL statements at once. Here it **creates two tables**:
  `accounts` and `transactions`, each with typed columns (`TEXT`, `REAL` = decimal number,
  `INTEGER`). `PRIMARY KEY` marks the unique id column.

```python
c.executemany("INSERT INTO accounts VALUES (?,?,?,?,?,?,?)", [
    ("C-1001", "Arjun Mehta",  "premium",   "current", 245000,  "Mumbai",  "verified"),
    ("C-1002", "Priya Nair",   "retail",    "savings",  18500,  "Chennai", "verified"),
    ("C-1003", "Deepak Shah",  "corporate", "current", 1200000, "Delhi",   "pending"),
])
c.executemany("INSERT INTO transactions VALUES (?,?,?,?,?,?)", [
    (1, "C-1001", "2026-06-10", "credit", 50000, "Salary credit"),
    (2, "C-1001", "2026-06-08", "debit",  12000, "Utility payment"),
    (3, "C-1001", "2026-06-05", "debit",  85000, "Wire transfer - flagged"),
    (4, "C-1002", "2026-06-09", "credit",  8000, "Freelance payment"),
    (5, "C-1003", "2026-06-07", "credit", 300000, "Invoice settlement"),
])
conn.commit(); conn.close()
print("Seeded", BANKING_DB)
```

- `c.executemany("INSERT ... VALUES (?,?,...)", [rows])` — insert **many rows** at once. Each `?` is
  a placeholder filled from the matching tuple. Using `?` placeholders (rather than gluing values
  into the SQL text) is the safe way — it prevents SQL-injection bugs.
- Note transaction #3 is a flagged ₹85,000 wire — that's what makes C-1001's fraud score high later.
- `conn.commit()` saves the changes; `conn.close()` closes the file.

> 🐍 **New idea — SQLite.** A complete SQL database in a single file, built into Python. `connect`
> opens it, a *cursor* runs SQL, `?` placeholders insert values safely, `commit` saves.

---

# Cell 18 — Write `banking_server.py` *(code)*

Same wrapper; the server inside reads the database and exposes banking tools, a resource, and a
prompt.

```python
import os, sqlite3
from _mcp_base import MCPServer

DB = os.environ.get("BANKING_DB") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "banking.db")

def q(sql, args=()):
    conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
    conn.close(); return rows

srv = MCPServer("banking-server")
```

- `DB = os.environ.get("BANKING_DB") or os.path.join(...)` — find the database: use the `BANKING_DB`
  environment variable if the client passed one, otherwise look for `banking.db` one folder up
  (`".."`) from this server file. `os.path.dirname(os.path.abspath(__file__))` is "the folder this
  script lives in."
- `def q(sql, args=()):` — a tiny helper to run a query and return rows as dicts.
  - `conn.row_factory = sqlite3.Row` — makes each row behave like a dict (access columns by name).
  - `[dict(r) for r in conn.execute(sql, args).fetchall()]` — run the query, fetch all rows, and turn
    each into a plain dict. `args` fills any `?` placeholders.

```python
@srv.tool("get_account", "Look up a customer's account by customer_id.",
          {"type": "object", "properties": {"customer_id": {"type": "string"}},
           "required": ["customer_id"]})
def get_account(customer_id):
    rows = q("SELECT * FROM accounts WHERE customer_id=?", (customer_id,))
    if not rows:
        return "No account for " + str(customer_id)
    a = rows[0]
    return (a["customer_id"] + " | " + a["name"] + " | " + a["segment"] + "/" + a["account_type"]
            + " | balance INR " + format(a["balance"], ",.0f") + " | " + a["city"]
            + " | KYC " + a["kyc_status"])
```

- `q("SELECT * FROM accounts WHERE customer_id=?", (customer_id,))` — fetch the matching account.
  `(customer_id,)` is a one-item tuple (the comma matters) filling the `?`.
- `if not rows:` — nothing found → friendly message. Otherwise `a = rows[0]` takes the first row and
  the return builds a readable one-line summary.

```python
@srv.tool("get_transactions", "Recent transactions for a customer (newest first).",
          {"type": "object",
           "properties": {"customer_id": {"type": "string"}, "limit": {"type": "integer"}},
           "required": ["customer_id"]})
def get_transactions(customer_id, limit=5):
    rows = q("SELECT * FROM transactions WHERE customer_id=? ORDER BY txn_date DESC LIMIT ?",
             (customer_id, int(limit)))
    if not rows:
        return "No transactions for " + str(customer_id)
    return "\n".join(r["txn_date"] + "  " + r["type"] + "  INR " + format(r["amount"], ",.0f")
                     + "  " + r["description"] for r in rows)
```

- Fetch recent transactions. `ORDER BY txn_date DESC` sorts newest first; `LIMIT ?` caps the count.
- The return joins each transaction into its own line with `"\n".join(... for r in rows)`.

```python
@srv.tool("fraud_risk_score", "Heuristic fraud-risk score (0-99) for a customer.",
          {"type": "object", "properties": {"customer_id": {"type": "string"}},
           "required": ["customer_id"]})
def fraud_risk_score(customer_id):
    rows = q("SELECT * FROM transactions WHERE customer_id=?", (customer_id,))
    if not rows:
        return "No transactions for " + str(customer_id)
    score = 10; signals = []
    for t in rows:
        if t["amount"] >= 80000:
            score += 35; signals.append("large txn " + format(t["amount"], ",.0f"))
        if "flag" in (t["description"] or "").lower():
            score += 40; signals.append("flagged: " + t["description"])
    score = min(score, 99)
    band = "HIGH" if score >= 70 else ("MEDIUM" if score >= 40 else "LOW")
    return ("Fraud risk for " + str(customer_id) + ": " + str(score) + "/100 (" + band + "). "
            + "Signals: " + (", ".join(signals) if signals else "none"))
```

- A simple **rules-based** score. Start at `score = 10` with an empty `signals` list.
- `for t in rows:` — examine each transaction. A large amount (`>= 80000`) adds 35; a description
  containing "flag" adds 40, and each reason is appended to `signals`. `(t["description"] or "")`
  guards against a missing description before `.lower()`.
- `score = min(score, 99)` — cap at 99. `band = "HIGH" if ... else ("MEDIUM" if ... else "LOW")` is a
  **chained ternary** picking a label. The return summarises the score, band, and signals.

```python
@srv.resource("policy://basel-iii", "Basel III capital-adequacy summary.")
def basel_iii():
    return ("Basel III: minimum CET1 4.5%, Tier 1 6%, total capital 8% of risk-weighted assets; "
            "capital conservation buffer 2.5%; LCR >= 100%; NSFR >= 100%.")

@srv.prompt("compliance_review", "Template: AML/KYC compliance review note for a customer.",
            ["customer_id"])
def compliance_review(customer_id):
    return ("Draft an AML/KYC compliance review for customer " + str(customer_id) + ". "
            "Check KYC status, flag transactions above regulatory thresholds, and recommend "
            "actions consistent with Basel III and RBI norms.")

srv.serve_forever()
```

- A **resource** (Basel III text) and a **prompt** template (compliance review). Then
  `serve_forever()` starts the server. So this one server exposes all three primitives plus a real
  database — the "domain server" pattern.

---

# Cell 19 — "3d · stateful_server.py" *(markdown)*

Explains the stateless/stateful toggle via the `MCP_MODE` environment variable. Nothing to run.

---

# Cell 20 — Write `stateful_server.py` *(code)*

Same wrapper; the server inside changes behaviour based on an environment variable.

```python
import os
from _mcp_base import MCPServer

MODE = os.environ.get("MCP_MODE", "stateless")
srv = MCPServer("stateful-server[" + MODE + "]")

_session = {"current_customer": None}
```

- `MODE = os.environ.get("MCP_MODE", "stateless")` — read the mode the client passed (via
  `env_extra`), defaulting to "stateless." The client sets this when spawning the server, which is how
  one file produces two behaviours.
- `_session = {...}` — a place to remember the current customer (only used in stateful mode).

```python
@srv.tool("set_current_customer", "Set the current customer for this session.",
          {"type": "object", "properties": {"customer_id": {"type": "string"}},
           "required": ["customer_id"]})
def set_current_customer(customer_id):
    if MODE == "stateful":
        _session["current_customer"] = customer_id
        return "[stateful] current customer stored server-side: " + str(customer_id)
    return "[stateless] received " + str(customer_id) + " but stateless servers keep no session state."

@srv.tool("get_current_customer", "Return the current session customer.",
          {"type": "object", "properties": {}})
def get_current_customer():
    if MODE == "stateful":
        return "[stateful] current customer is " + str(_session["current_customer"])
    return "[stateless] no session memory - the client must pass customer_id on every call."

srv.serve_forever()
```

- `set_current_customer` — in **stateful** mode it stores the id in `_session` and confirms;
  in **stateless** mode it deliberately does *not* store it.
- `get_current_customer` — in stateful mode returns the remembered id; in stateless mode explains
  there's no memory. Note its schema has empty `properties` (no arguments).
- Running the same file twice with different `MODE` is what makes Pattern 7's contrast possible.

> 🐍 **New idea — behaviour from the environment.** A program can read environment variables to
> change what it does without changing its code. Here, one file is both the stateless *and* the
> stateful server, depending on `MCP_MODE`.

---

# Cell 21 — "Part 4 · The ReAct agent" *(markdown)*

Explains the loop that lets Claude drive the servers (discover tools, call them, feed results back),
plus the remote connector and sampling helper. Nothing to run.

---

# Cell 22 — The agent core: `llm`, `mcp_tools_to_anthropic`, `run_agent` *(code)*

**What it does:** defines the ReAct loop that connects Claude to the MCP servers.

```python
_llm = None
def llm():
    global _llm
    if _llm is None:
        if anthropic is None:
            raise RuntimeError("anthropic package not installed")
        _llm = anthropic.Anthropic(api_key=API_KEY)
    return _llm
```

- `_llm = None` then `def llm():` — **lazy, one-time setup.** The first time `llm()` is called it
  creates the Anthropic client and stores it in `_llm`; later calls reuse it.
- `global _llm` — tells Python to update the module-level `_llm`, not make a new local variable.
- `if anthropic is None: raise RuntimeError(...)` — a clear error if the SDK isn't installed. (Pattern
  cells only call `llm()` when `have_key()` is true, so this rarely triggers.)

```python
MAX_ITERS = 8

def mcp_tools_to_anthropic(mcp_clients):
    tools, route = [], {}
    for mc in mcp_clients:
        for t in mc.list_tools():
            tools.append({"name": t["name"], "description": t["description"],
                          "input_schema": t["inputSchema"]})
            route[t["name"]] = mc
    return tools, route
```

- `MAX_ITERS = 8` — a safety cap so the loop can't run forever.
- `mcp_tools_to_anthropic(mcp_clients)` — take one or more MCP clients and build two things:
  - `tools` — a list of tool schemas in **Anthropic's** format (note `input_schema` with an
    underscore, vs MCP's `inputSchema`). This is the small translation between the two worlds.
  - `route` — a dictionary mapping each tool name to the client that owns it, so a call can be sent to
    the right server. This is what makes **multi-server** orchestration work.

```python
def run_agent(question, model, mcp_clients, system=None):
    tools, route = mcp_tools_to_anthropic(mcp_clients)
    messages = [{"role": "user", "content": question}]
    log, answer = [], ""
    usage = {"input_tokens": 0, "output_tokens": 0}
    sys_prompt = system or ("You are a helpful assistant. Use the available MCP tools when they "
                            "give better or real-time data. Explain briefly which tool you use and why.")
```

- `run_agent(...)` — the loop. Build the tools + routing map, start the conversation with the user's
  `question`, and prepare empty `log`, `answer`, and `usage` counters.
- `sys_prompt = system or (...)` — use the caller's system instruction, or a sensible default.

```python
    for _ in range(MAX_ITERS):
        resp = llm().messages.create(
            model=model, max_tokens=1500, system=sys_prompt,
            tools=tools if tools else [], messages=messages)
        usage["input_tokens"]  += resp.usage.input_tokens
        usage["output_tokens"] += resp.usage.output_tokens
```

- `for _ in range(MAX_ITERS):` — loop up to 8 times. `_` is a throwaway name (we don't need the
  counter).
- `resp = llm().messages.create(...)` — **call Claude** with the model, the system prompt, the tools,
  and the conversation so far. `tools if tools else []` passes an empty list if there are no tools.
- The two `usage[...] += ...` lines accumulate token counts across loops.

```python
        for b in resp.content:
            if b.type == "text" and b.text.strip():
                log.append(("thought", b.text.strip())); answer = b.text.strip()

        if resp.stop_reason != "tool_use":
            break
```

- Claude's reply is a list of **content blocks** (`resp.content`). This loop records any *text* block
  as a "thought" and keeps the latest as the running `answer`.
- `if resp.stop_reason != "tool_use": break` — if Claude did **not** ask to use a tool, it's finished
  → leave the loop.

```python
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for b in resp.content:
            if b.type != "tool_use":
                continue
            mc = route.get(b.name)
            srv_name = mc.name if mc else "?"
            log.append(("action", f"call {b.name} on [{srv_name}]  args={json.dumps(b.input)}"))
            out = json.dumps({"error": f"no server owns tool {b.name}"}) if mc is None \
                  else mc.call_tool(b.name, b.input)
            log.append(("observation", out))
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": out})
        messages.append({"role": "user", "content": results})
```

- If we're still here, Claude asked to call at least one tool. First, add Claude's message to the
  history. Then loop its blocks and handle each `tool_use`:
  - `mc = route.get(b.name)` — find which client/server owns the requested tool.
  - Record an "action" line naming the tool, the server, and the arguments (`b.input`).
  - `out = ... if mc is None else mc.call_tool(b.name, b.input)` — if no server owns it, produce an
    error; otherwise **call the tool** on the right server and capture the text.
  - Record the "observation" (the result), and build a `tool_result` block carrying `b.id` (the
    `tool_use_id` links the result back to Claude's request).
- `messages.append({"role": "user", "content": results})` — send all tool results back to Claude as
  the next user turn. The loop repeats so Claude can use them (and maybe call more tools).

```python
    cost = usage["input_tokens"]/1e6*3 + usage["output_tokens"]/1e6*15
    return {"answer": answer, "log": log, "usage": usage, "cost_usd": round(cost, 6)}

print("run_agent ready.")
```

- `cost = ...` — a rough dollar estimate using Sonnet pricing (about $3 per million input tokens, $15
  per million output). `/1e6` divides by a million.
- The function returns the answer, the step log, token usage, and the cost.

> 🐍 **New idea — the ReAct loop.** "Reason + Act": Claude *thinks*, optionally *acts* (calls a
> tool), *observes* the result, and repeats until it has an answer. The `while`-style `for` loop with
> `break` on `stop_reason != "tool_use"` is that pattern in code.

---

# Cell 23 — Remote connector & sampling: `run_remote_mcp`, `mcp_sampling_demo` *(code)*

**What it does:** defines the two special patterns — connecting to a remote MCP server, and the
sampling round-trip.

```python
def run_remote_mcp(question, model, server_url, token=None):
    if not server_url:
        return {"answer": "No REMOTE_MCP_URL configured. Set it in .env to try a live remote MCP server.",
                "log": [("info", "Remote MCP demo skipped -- no URL set.")], "usage": {}, "cost_usd": 0}
    mcp_server = {"type": "url", "url": server_url, "name": "remote-mcp"}
    if token:
        mcp_server["authorization_token"] = token
    try:
        resp = llm().beta.messages.create(
            model=model, max_tokens=1200,
            messages=[{"role": "user", "content": question}],
            mcp_servers=[mcp_server], betas=["mcp-client-2025-11-20"])
        answer = " ".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return {"answer": answer or "(no text)",
                "log": [("info", f"Connected to remote MCP: {server_url}"),
                        ("observation", "Tool discovery + calls handled server-side by Anthropic.")],
                "usage": {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens},
                "cost_usd": 0}
    except Exception as e:
        return {"answer": f"Remote MCP error: {e}",
                "log": [("info", f"Failed to reach {server_url}: {e}")], "usage": {}, "cost_usd": 0}
```

- `if not server_url:` — if no remote URL was provided, return a friendly "skipped" result. That's
  why this pattern runs safely even with nothing configured.
- `mcp_server = {...}` — describe the remote server; add a `token` only if one was given.
- `resp = llm().beta.messages.create(..., mcp_servers=[...], betas=[...])` — call Claude's **beta MCP
  connector**, which connects to the remote server *on Anthropic's side* — your code doesn't proxy the
  tool calls.
- `answer = " ".join(b.text for b in resp.content if getattr(b, "type", "") == "text")` — join all
  text blocks. `getattr(b, "type", "")` reads `b.type` safely (returns `""` if the attribute is
  missing).
- `except Exception as e:` — network problems are returned as an error result, not a crash.

```python
def mcp_sampling_demo(text_to_summarise, model):
    sampling_request = {
        "method": "sampling/createMessage",
        "params": {"messages": [{"role": "user",
                                  "content": {"type": "text",
                                              "text": f"Summarise in one sentence: {text_to_summarise}"}}],
                   "maxTokens": 100, "modelPreferences": {"hints": [{"name": model}]}}}
    log = [("action", "SERVER -> CLIENT  sampling/createMessage"),
           ("observation", json.dumps(sampling_request, indent=2))]
    try:
        resp = llm().messages.create(
            model=model, max_tokens=120,
            messages=[{"role": "user",
                       "content": sampling_request["params"]["messages"][0]["content"]["text"]}])
        summary = " ".join(b.text for b in resp.content if b.type == "text")
        log.append(("thought", "CLIENT fulfils the sampling request with a real Claude call."))
        log.append(("observation", f"CLIENT -> SERVER  result: {summary}"))
        return {"answer": summary, "log": log,
                "usage": {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens},
                "cost_usd": 0}
    except Exception as e:
        return {"answer": f"Sampling error: {e}", "log": log, "usage": {}, "cost_usd": 0}

print("run_remote_mcp and mcp_sampling_demo ready.")
```

- `sampling_request = {...}` — the request the **server** would send **to the client** (note the
  reverse direction). It asks the client's LLM to summarise the text.
- `log = [...]` — record that reverse message for display.
- `resp = llm().messages.create(...)` — the **client fulfils it** with a real Claude call, reaching
  into the request to get the exact text to summarise.
- `summary = " ".join(...)` — collect Claude's text answer, log it, and return it. On failure, return
  an error result.

---

# Cell 24 — "Long-lived clients" *(markdown)*

Explains that each server is started once and reused, via a cache. Nothing to run.

---

# Cell 25 — `get_client` and the client cache *(code)*

```python
CLIENTS = {}
def get_client(key, filename, env_extra=None):
    c = CLIENTS.get(key)
    if c is None or not c.is_alive():
        c = MCPClient(os.path.join(SERVERS, filename), env_extra=env_extra, name=key).start()
        CLIENTS[key] = c
    return c

print("get_client ready. Servers will start on first use.")
```

- `CLIENTS = {}` — a dictionary caching started clients, keyed by a short name.
- `get_client(key, filename, env_extra=None)` — return a running client for a server:
  - `c = CLIENTS.get(key)` — is one already cached?
  - `if c is None or not c.is_alive():` — if not (or it died), create a new `MCPClient` pointing at
    `mcp_servers/<filename>`, `.start()` it (spawns the subprocess + handshake), and cache it.
  - `return c` — hand back the (now running) client.
- This is why running a pattern twice is fast: the server is already up.

---

# Cell 26 — "The eight MCP server patterns" *(markdown)*

A table mapping each pattern to its primitives and server(s). Nothing to run.

---

# Cell 27 — "Pattern 1" *(markdown)*

Explains the local stdio server with all three primitives. Nothing to run.

---

# Cell 28 — Pattern 1: local stdio server *(code)*

**What it does:** starts the general server, lists its tools, and answers a question — via Claude if
a key is set, otherwise by calling the tools directly.

```python
question = "Convert 100 km to miles and give me a stock quote for INFY."
c = get_client("general", "general_server.py"); c.clear_trace()
print("Tools on general-server:", [t["name"] for t in c.list_tools()])

if have_key():
    r = run_agent(question, MODEL, [c]); print_answer(r); print_log(r["log"])
else:
    print("\n(No API key -> calling the tools directly so you still see them run)")
    print("  ", c.call_tool("convert_units", {"value": 100, "from_unit": "km", "to_unit": "miles"}))
    print("  ", c.call_tool("get_stock_quote", {"symbol": "INFY"}))

print_trace(c)
```

- `question = "..."` — the request to answer.
- `c = get_client("general", "general_server.py")` — start (or reuse) the general server;
  `c.clear_trace()` empties its message log so the trace shows only this run.
- `print("Tools ...", [t["name"] for t in c.list_tools()])` — discover and print the tool names.
- `if have_key():` — with a key, run the **agent** (Claude decides which tools to call) and print the
  answer and steps.
- `else:` — without a key, **call the tools directly** so the demo still works and the wire trace
  still fills. Notice these are the exact calls Claude would make.
- `print_trace(c)` — show the JSON-RPC messages.

> 🐍 **New idea — the graceful fallback.** Every agentic pattern uses this `if have_key(): ... else:
> direct calls` shape, so the notebook always demonstrates the MCP mechanics — with or without Claude.

---

# Cell 29 — "Pattern 2" *(markdown)*

Explains the remote MCP connector (needs `REMOTE_MCP_URL`). Nothing to run.

---

# Cell 30 — Pattern 2: remote MCP connector *(code)*

```python
url = os.environ.get("REMOTE_MCP_URL", ""); tok = os.environ.get("REMOTE_MCP_TOKEN", "")
if have_key() or not url:
    r = run_remote_mcp("What tools does this remote MCP server expose?", MODEL, url, tok)
    print_answer(r); print_log(r["log"])
else:
    print("A remote URL is set but no API key -> the connector call needs a key. Skipping the live call.")
```

- Read the optional remote URL and token from the environment.
- `if have_key() or not url:` — run `run_remote_mcp` when we have a key, **or** when there's no URL
  (in which case it just returns the friendly "skipped" message). Either way it's safe to call.
- The `else` covers the one case where a URL is set but no key exists.

---

# Cell 31 — "Pattern 3" *(markdown)*

Explains multi-server orchestration (fan-out across two servers). Nothing to run.

---

# Cell 32 — Pattern 3: multi-server orchestration *(code)*

```python
question = "Convert 5 km to miles, then compute compound interest on 100000 at 8% for 5 years."
gen = get_client("general", "general_server.py"); gen.clear_trace()
mth = get_client("math", "math_server.py"); mth.clear_trace()
print("general tools:", [t["name"] for t in gen.list_tools()])
print("math tools   :", [t["name"] for t in mth.list_tools()])

if have_key():
    r = run_agent(question, MODEL, [gen, mth]); print_answer(r); print_log(r["log"])
else:
    print("\n(No API key -> calling one tool on EACH server directly)")
    print("  ", gen.call_tool("convert_units", {"value": 5, "from_unit": "km", "to_unit": "miles"}))
    print("  ", mth.call_tool("compound_interest", {"principal": 100000, "rate": 8, "years": 5}))

print("\n===== general-server trace ====="); print_trace(gen)
print("\n===== math-server trace ====="); print_trace(mth)
```

- Start **two** servers (`gen` and `mth`) and list each one's tools.
- With a key, `run_agent(question, MODEL, [gen, mth])` passes **both** clients to the agent. Inside
  `run_agent`, the routing map sends `convert_units` to the general server and `compound_interest` to
  the math server automatically — that's the fan-out.
- Without a key, we call one tool on each server directly.
- Two `print_trace(...)` calls show that each server only handled its own messages.

---

# Cell 33 — "Pattern 4" *(markdown)*

Explains resources (read-only data, no LLM). Nothing to run.

---

# Cell 34 — Pattern 4: resources *(code)*

```python
c = get_client("general", "general_server.py"); c.clear_trace()
print("Resources on general-server:", [r["uri"] for r in c.list_resources()])
for uri in ["policy://kyc-summary", "customer://C-1001"]:
    print("\n" + uri + " ->")
    print("  ", c.read_resource(uri))
print_trace(c)
```

- List the resource URIs, then loop over two of them and `read_resource(uri)` each. No API key is
  needed — reading a resource is a pure data pull (like a `GET`). The trace shows `resources/list`
  and `resources/read` messages.

---

# Cell 35 — "Pattern 5" *(markdown)*

Explains prompt templates. Nothing to run.

---

# Cell 36 — Pattern 5: prompt templates *(code)*

```python
c = get_client("general", "general_server.py"); c.clear_trace()
print("Prompts on general-server:", [p["name"] for p in c.list_prompts()])
rendered = c.get_prompt("structured_analysis",
                        {"topic": "the benefits of MCP servers", "audience": "beginners"})
print("\nRendered template:\n" + rendered)

if have_key():
    r = run_agent(rendered, MODEL, [])
    print("\nClaude's response:\n" + r["answer"])

print_trace(c)
```

- List the prompt names, then `get_prompt(...)` renders the `structured_analysis` template with the
  given `topic` and `audience` (the server fills the slots). The render needs no key.
- If a key is set, we feed the rendered prompt to Claude with `run_agent(rendered, MODEL, [])` — an
  **empty** tools list (`[]`), because here we just want Claude to answer the prompt, not call tools.

---

# Cell 37 — "Pattern 6" *(markdown)*

Explains sampling (server borrows the client's LLM — reverse direction). Nothing to run.

---

# Cell 38 — Pattern 6: sampling *(code)*

```python
text = ("MCP is an open standard that lets any AI agent connect to any tool or data source "
        "through one universal protocol.")
if have_key():
    r = mcp_sampling_demo(text, MODEL); print_answer(r); print_log(r["log"])
else:
    print("(No API key -> showing the sampling request the SERVER would send to the CLIENT)")
    sampling_request = {
        "method": "sampling/createMessage",
        "params": {"messages": [{"role": "user",
                                  "content": {"type": "text", "text": f"Summarise in one sentence: {text}"}}],
                   "maxTokens": 100, "modelPreferences": {"hints": [{"name": MODEL}]}}}
    print(json.dumps(sampling_request, indent=2))
    print("\nThe client would run its LLM on that request and return the summary to the server.")
```

- With a key, run the real sampling round-trip via `mcp_sampling_demo`.
- Without a key, **print the request shape** the server would send — so students still learn the wire
  format for `sampling/createMessage` even though we skip the live LLM call.

---

# Cell 39 — "Pattern 7" *(markdown)*

Explains stateless vs stateful servers. Nothing to run.

---

# Cell 40 — Pattern 7: stateless vs stateful *(code)*

```python
for mode in ["stateless", "stateful"]:
    c = get_client("stateful_" + mode, "stateful_server.py", env_extra={"MCP_MODE": mode})
    c.clear_trace()
    print("===== MODE:", mode, "=====")
    print("  set:", c.call_tool("set_current_customer", {"customer_id": "C-1001"}))
    print("  get:", c.call_tool("get_current_customer", {}))
    print()

print_trace(get_client("stateful_stateful", "stateful_server.py", env_extra={"MCP_MODE": "stateful"}))
```

- `for mode in ["stateless", "stateful"]:` — run the demo twice, once per mode.
- `get_client("stateful_" + mode, "stateful_server.py", env_extra={"MCP_MODE": mode})` — start the
  **same server file** but pass a different `MCP_MODE` each time via `env_extra`. Because the cache
  keys differ (`stateful_stateless` vs `stateful_stateful`), you get **two separate processes**.
- We call `set_current_customer` then `get_current_customer` and print both results. In stateless
  mode the "get" shows no memory; in stateful mode it returns C-1001 — the whole point of the pattern.
- The final `print_trace(...)` shows the JSON-RPC for the stateful server. No API key needed anywhere
  here.

---

# Cell 41 — "Pattern 8" *(markdown)*

Explains the banking domain server. Nothing to run.

---

# Cell 42 — Pattern 8: banking domain server *(code)*

```python
c = get_client("banking", "banking_server.py",
               env_extra={"BANKING_DB": os.path.join(ROOT, "banking.db")}); c.clear_trace()
print("Banking tools:", [t["name"] for t in c.list_tools()])
question = "Look up customer C-1001, show their recent transactions, and give me their fraud risk score."

if have_key():
    r = run_agent(question, MODEL, [c],
                  system="You are a banking assistant. Use the banking MCP tools to answer. "
                         "Be precise with figures and cite the customer_id.")
    print_answer(r); print_log(r["log"])
else:
    print("\n(No API key -> calling the banking tools directly)")
    print(c.call_tool("get_account", {"customer_id": "C-1001"}))
    print(c.call_tool("get_transactions", {"customer_id": "C-1001"}))
    print(c.call_tool("fraud_risk_score", {"customer_id": "C-1001"}))
    print("\nResource policy://basel-iii ->")
    print("  ", c.read_resource("policy://basel-iii"))

print_trace(c)
```

- `get_client("banking", ..., env_extra={"BANKING_DB": os.path.join(ROOT, "banking.db")})` — start
  the banking server, telling it exactly where the database file is via the `BANKING_DB` environment
  variable.
- With a key, the agent runs with a **custom system prompt** telling Claude to act as a banking
  assistant and chain the tools.
- Without a key, we call the three tools directly (account, transactions, fraud score) and also read
  the Basel III resource — showing this one server exposes tools *and* a resource, all backed by
  SQLite.

---

# Cell 43 — "Compare patterns" *(markdown)*

Explains running the same question through patterns 1 / 3 / 8. Nothing to run.

---

# Cell 44 — Compare patterns 1 / 3 / 8 *(code)*

```python
question = "What is customer C-1001's fraud risk score?"
bank = get_client("banking", "banking_server.py",
                  env_extra={"BANKING_DB": os.path.join(ROOT, "banking.db")}); bank.clear_trace()

if have_key():
    gen = get_client("general", "general_server.py"); gen.clear_trace()
    r1 = run_agent(question, MODEL, [gen])
    gen.clear_trace(); mth = get_client("math", "math_server.py"); mth.clear_trace()
    r3 = run_agent(question, MODEL, [gen, mth])
    r8 = run_agent(question, MODEL, [bank])
    print("| Pattern | Answer (short) | In tok | Out tok | Cost |")
    print("|---|---|---|---|---|")
    for name, r in [("P1 single", r1), ("P3 multi", r3), ("P8 banking", r8)]:
        print(f"| {name} | {r['answer'][:50]}... | {r['usage'].get('input_tokens',0)} "
              f"| {r['usage'].get('output_tokens',0)} | ${r['cost_usd']:.5f} |")
else:
    print("(No API key -> the pure-MCP answer from the banking server:)")
    print("  ", bank.call_tool("fraud_risk_score", {"customer_id": "C-1001"}))
    print("\nWith a key, this cell runs the same question through patterns 1, 3, and 8 and compares cost.")
```

- With a key, run the **same question** three ways — single server (general), multi-server
  (general + math), and banking — then print a Markdown table of the short answer, token counts, and
  cost for each. The `for name, r in [...]:` loop builds one table row per pattern; `r['answer'][:50]`
  shows the first 50 characters.
- Without a key, just show the banking server's direct fraud-score answer, and note what the full
  comparison would do.

---

# Cell 45 — "Server status" *(markdown)*

Explains the live-process status view. Nothing to run.

---

# Cell 46 — Server status *(code)*

```python
def server_status():
    if not CLIENTS:
        print("No servers started yet -- run a pattern cell first."); return
    print(f"{'server':22} {'alive':6} {'pid':7} {'uptime':8} tools/res/prompts")
    print("-" * 60)
    for key, c in CLIENTS.items():
        if c.is_alive():
            nt = len(c.list_tools()); nr = len(c.list_resources()); npr = len(c.list_prompts())
            print(f"{key:22} {'yes':6} {str(c.pid):7} {str(c.uptime):8} {nt}/{nr}/{npr}")
        else:
            print(f"{key:22} {'no':6} {'-':7} {'-':8} -")

server_status()
```

- `server_status()` prints a table of every started server. `if not CLIENTS:` handles the "nothing
  started yet" case.
- The `f"{'server':22}"` syntax **pads** text to a fixed width (22 characters) so the columns line up.
- For each alive server it counts tools/resources/prompts (`nt`/`nr`/`npr`) with `len(...)` and prints
  the row; dead ones show dashes. `"-" * 60` prints a 60-character divider line.
- The last line calls the function so the table prints immediately.

> 🐍 **New idea — fixed-width formatting.** `f"{value:22}"` reserves 22 characters for `value`,
> padding with spaces. It's the simplest way to make columns line up in plain-text output.

---

# Cell 47 — "Cleanup" *(markdown)*

Says to run the next cell when finished. Nothing to run yet.

---

# Cell 48 — Cleanup: stop the servers *(code)*

```python
for key, c in list(CLIENTS.items()):
    try: c.stop()
    except Exception: pass
print("Stopped", len(CLIENTS), "MCP server subprocess(es).")
```

- `for key, c in list(CLIENTS.items()):` — loop over every cached client. Wrapping in `list(...)`
  makes a snapshot so we can safely iterate while stopping things.
- `try: c.stop() except Exception: pass` — stop each server; ignore any error (it may already be
  gone).
- The final line reports how many were stopped. Run this at the end of class to leave no stray
  processes behind.

---

# Cell 49 — Recap & cheat sheet *(markdown)*

The one-page summary: the JSON-RPC contract, the three primitives by control model, the two advanced
moves (sampling, stateless vs stateful), the pattern behind every cell, and homework. Nothing to run
— it's your revision card.

---

## The six things to leave the class with

1. **Every MCP message is JSON-RPC 2.0.** Request has `method` + `params`; response has `result` or
   `error`; `id` pairs them. That contract never changes.
2. **`MCPServer.handle()` is the whole server.** One method reads `method` and returns the right
   response. Everything a server exposes is a function **registered by a decorator**.
3. **Three primitives, by who controls them.** Tools → the model acts; Resources → the app reads;
   Prompts → the user picks a template.
4. **Two advanced moves.** Sampling → the server borrows the *client's* LLM (reverse direction).
   Stateless vs stateful → stateless servers keep no memory, so they scale like web services.
5. **The client is two programs talking.** `subprocess.Popen` launches the server; the client writes
   a JSON line to its stdin and reads a JSON line from its stdout. The `trace` list is what lets us
   *see* it.
6. **The Python patterns repeat.** Register functions with `@srv.tool/resource/prompt`; the client
   wraps `_request`; the agent loops "think → act → observe." Once you see those three shapes, every
   cell is familiar.

*Tip for teaching: run the pure-MCP patterns (4, 5, 7) first — they need no API key and make the
wire protocol obvious. Then, with a key set, re-run patterns 1, 3, and 8 to show Claude choosing the
tools itself.*
