"""
mcp_client.py  —  A tiny MCP CLIENT that spawns a stdio server subprocess and
speaks JSON-RPC 2.0 to it. Records every message into a trace list so the
Gradio UI can show the full wire protocol.

In production you would use the official `mcp` SDK ClientSession instead;
the message shapes are identical to what this client sends/receives.
"""
import subprocess, sys, json, threading, time, os

class MCPClient:
    def __init__(self, server_path, env_extra=None, name=None):
        self.server_path = server_path
        self.name = name or os.path.basename(server_path)
        self.env_extra = env_extra or {}
        self.proc = None
        self._id = 0
        self._lock = threading.Lock()
        self.trace = []          # list of {"dir": "->"/"<-", "msg": {...}}
        self.started_at = None

    # ---- lifecycle ----
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

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try: self.proc.wait(timeout=3)
            except Exception: self.proc.kill()

    def is_alive(self):
        return self.proc is not None and self.proc.poll() is None

    @property
    def pid(self):
        return self.proc.pid if self.proc else None

    @property
    def uptime(self):
        return round(time.time() - self.started_at, 1) if self.started_at else 0

    # ---- JSON-RPC ----
    def _request(self, method, params=None, timeout=15):
        with self._lock:
            self._id += 1
            req = {"jsonrpc": "2.0", "id": self._id, "method": method,
                   "params": params or {}}
            self.trace.append({"dir": "->", "msg": req})
            try:
                self.proc.stdin.write(json.dumps(req) + "\n")
                self.proc.stdin.flush()
                line = self.proc.stdout.readline()
                if not line:
                    err = {"error": "no response (server may have crashed)"}
                    self.trace.append({"dir": "<-", "msg": err})
                    return err
                resp = json.loads(line.strip())
                self.trace.append({"dir": "<-", "msg": resp})
                return resp
            except Exception as e:
                err = {"error": f"transport error: {e}"}
                self.trace.append({"dir": "<-", "msg": err})
                return err

    # ---- MCP primitives ----
    def list_tools(self):
        r = self._request("tools/list")
        return r.get("result", {}).get("tools", [])

    def call_tool(self, name, arguments):
        r = self._request("tools/call", {"name": name, "arguments": arguments})
        if "error" in r:
            return json.dumps(r["error"])
        content = r.get("result", {}).get("content", [])
        return "\n".join(c.get("text", "") for c in content)

    def list_resources(self):
        r = self._request("resources/list")
        return r.get("result", {}).get("resources", [])

    def read_resource(self, uri):
        r = self._request("resources/read", {"uri": uri})
        contents = r.get("result", {}).get("contents", [])
        return "\n".join(c.get("text", "") for c in contents)

    def list_prompts(self):
        r = self._request("prompts/list")
        return r.get("result", {}).get("prompts", [])

    def get_prompt(self, name, arguments):
        r = self._request("prompts/get", {"name": name, "arguments": arguments})
        msgs = r.get("result", {}).get("messages", [])
        return "\n".join(m.get("content", {}).get("text", "") for m in msgs)

    def clear_trace(self):
        self.trace = []
