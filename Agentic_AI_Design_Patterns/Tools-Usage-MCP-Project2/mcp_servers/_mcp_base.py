"""
_mcp_base.py  —  Minimal MCP server framework (JSON-RPC 2.0 over stdio).

WHY A MINI-FRAMEWORK?
=====================
The official `mcp` / FastMCP SDK is the production choice (decorators:
@mcp.tool / @mcp.resource / @mcp.prompt). We re-implement the wire protocol
in ~120 lines here so the project runs with ZERO extra dependencies and so
learners can SEE every JSON-RPC message that flows. In production, swap this
for FastMCP — the message shapes are identical.

MCP WIRE PROTOCOL (JSON-RPC 2.0 over stdin/stdout)
==================================================
  CLIENT (agent)                          SERVER (this process)
       |  --- initialize -------------------->  |
       |  <-- serverInfo + capabilities ------  |
       |  --- tools/list -------------------->  |
       |  <-- [tool schemas] ----------------   |
       |  --- tools/call {name,args} -------->  |
       |  <-- {content:[{type:text,...}]} ---   |
       |  --- resources/list ---------------->  |
       |  <-- [resource descriptors] --------   |
       |  --- resources/read {uri} ---------->  |
       |  <-- {contents:[{uri,text}]} -------    |
       |  --- prompts/list ------------------>  |
       |  <-- [prompt descriptors] ----------   |
       |  --- prompts/get {name,args} ------->  |
       |  <-- {messages:[...]} --------------    |
"""
import sys, json

class MCPServer:
    def __init__(self, name, version="1.0.0"):
        self.name = name
        self.version = version
        self._tools = {}       # name -> (schema_dict, fn)
        self._resources = {}   # uri  -> (descriptor_dict, fn)
        self._prompts = {}     # name -> (descriptor_dict, fn)

    # ---- registration helpers ----
    def tool(self, name, description, input_schema):
        def deco(fn):
            self._tools[name] = ({
                "name": name, "description": description,
                "inputSchema": input_schema}, fn)
            return fn
        return deco

    def resource(self, uri, name, description, mime="text/plain"):
        def deco(fn):
            self._resources[uri] = ({
                "uri": uri, "name": name,
                "description": description, "mimeType": mime}, fn)
            return fn
        return deco

    def prompt(self, name, description, arguments):
        def deco(fn):
            self._prompts[name] = ({
                "name": name, "description": description,
                "arguments": arguments}, fn)
            return fn
        return deco

    # ---- JSON-RPC plumbing ----
    @staticmethod
    def _send(obj):
        sys.stdout.write(json.dumps(obj) + "\n"); sys.stdout.flush()

    def _ok(self, rid, result):
        self._send({"jsonrpc": "2.0", "id": rid, "result": result})

    def _err(self, rid, code, msg):
        self._send({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": msg}})

    def run(self):
        """Main stdio loop: read a JSON-RPC request per line, dispatch, reply."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._dispatch(msg)

    def _dispatch(self, msg):
        method = msg.get("method", "")
        rid    = msg.get("id")
        params = msg.get("params", {})

        if method == "initialize":
            self._ok(rid, {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                "serverInfo": {"name": self.name, "version": self.version},
            })

        elif method == "tools/list":
            self._ok(rid, {"tools": [s for s, _ in self._tools.values()]})

        elif method == "tools/call":
            tname = params.get("name"); args = params.get("arguments", {})
            if tname not in self._tools:
                return self._err(rid, -32602, f"Unknown tool: {tname}")
            try:
                out = self._tools[tname][1](**args)
                text = out if isinstance(out, str) else json.dumps(out)
                self._ok(rid, {"content": [{"type": "text", "text": text}]})
            except Exception as e:
                self._ok(rid, {"content": [{"type": "text",
                    "text": json.dumps({"error": str(e)})}], "isError": True})

        elif method == "resources/list":
            self._ok(rid, {"resources": [d for d, _ in self._resources.values()]})

        elif method == "resources/read":
            uri = params.get("uri")
            if uri not in self._resources:
                return self._err(rid, -32602, f"Unknown resource: {uri}")
            text = self._resources[uri][1]()
            self._ok(rid, {"contents": [{"uri": uri, "mimeType":
                self._resources[uri][0]["mimeType"], "text": text}]})

        elif method == "prompts/list":
            self._ok(rid, {"prompts": [d for d, _ in self._prompts.values()]})

        elif method == "prompts/get":
            pname = params.get("name"); args = params.get("arguments", {})
            if pname not in self._prompts:
                return self._err(rid, -32602, f"Unknown prompt: {pname}")
            rendered = self._prompts[pname][1](**args)
            self._ok(rid, {"messages": [
                {"role": "user", "content": {"type": "text", "text": rendered}}]})

        elif method.startswith("notifications/"):
            pass  # no response required for notifications

        else:
            self._err(rid, -32601, f"Method not found: {method}")
