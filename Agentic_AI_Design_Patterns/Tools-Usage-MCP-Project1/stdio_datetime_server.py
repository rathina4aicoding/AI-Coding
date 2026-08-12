
# stdio_datetime_server.py
# A STANDALONE MCP server: reads JSON-RPC from stdin, writes JSON-RPC to stdout.
# The client (this notebook) launches it as a subprocess -- they talk over pipes.

import sys, json
from datetime import datetime

TOOLS = [{
    "name": "get_current_datetime",
    "description": "Returns current date/time in the given strftime format.",
    "inputSchema": {
        "type": "object",
        "properties": {"date_format": {"type": "string"}},
        "required": ["date_format"],
    },
}]

def handle(req):
    m, rid, params = req.get("method"), req.get("id"), req.get("params") or {}
    if m == "initialize":
        res = {"protocolVersion": "2024-11-05",
               "serverInfo": {"name": "stdio-datetime", "version": "1.0.0"},
               "capabilities": {"tools": {}}}
    elif m == "tools/list":
        res = {"tools": TOOLS}
    elif m == "tools/call":
        fmt = (params.get("arguments") or {}).get("date_format", "%Y-%m-%d %H:%M:%S")
        res = {"content": [{"type": "text", "text": datetime.now().strftime(fmt)}], "isError": False}
    else:
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32601, "message": "Unknown method"}}
    return {"jsonrpc": "2.0", "id": rid, "result": res}

for line in sys.stdin:               # blocks, waiting for each request line
    line = line.strip()
    if not line:
        continue
    sys.stdout.write(json.dumps(handle(json.loads(line))) + "\n")
    sys.stdout.flush()               # must flush or the pipe blocks
