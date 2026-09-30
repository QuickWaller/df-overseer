"""Live MCP client for VM 103 checks. Run from /opt/df/dfmcp-smoke/.venv.

  mcpcall.py counts                      -> tool count per role
  mcpcall.py names ROLE [SUBSTR]         -> tool names for a role
  mcpcall.py call ROLE TOOL 'JSON_ARGS'  -> one tool call, prints text result

Token read by key from .env, never printed. Address from `hostname -I`,
never printed.
"""
import asyncio, json, subprocess, sys

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
import httpx2 as httpx  # this install vendors httpx as httpx2 (docs/TRAPS.md)

ENV = "/opt/df/dfmcp-smoke/.env"
ROLES = ["overseer", "architect", "consultant", "quartermaster", "conductor"]


def token(role):
    key = "MCP_ROLE_TOKEN_" + role.upper() + "="
    for line in open(ENV):
        if line.startswith(key):
            return line[len(key):].strip().strip('"').strip("'")
    raise SystemExit("no token for " + role)


def url():
    ip = subprocess.check_output(["hostname", "-I"], text=True).split()[0]
    return "http://" + ip + ":8443/mcp"


async def session(role, fn):
    client = httpx.AsyncClient(headers={"Authorization": "Bearer " + token(role)}, timeout=120)
    async with streamable_http_client(url(), http_client=client) as (r, w, *_):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return await fn(s)


async def main():
    mode = sys.argv[1]
    if mode == "counts":
        for role in ROLES:
            tools = await session(role, lambda s: s.list_tools())
            print(role, len(tools.tools))
    elif mode == "names":
        role = sys.argv[2]
        sub = sys.argv[3] if len(sys.argv) > 3 else ""
        tools = await session(role, lambda s: s.list_tools())
        for t in tools.tools:
            if sub in t.name:
                print(t.name)
    elif mode == "schema":
        role, tool = sys.argv[2], sys.argv[3]
        tools = await session(role, lambda s: s.list_tools())
        for t in tools.tools:
            if t.name == tool:
                print(json.dumps(t.input_schema.get("properties"), indent=0)[:3000]); print("required", t.input_schema.get("required"))
    elif mode == "call":
        role, tool, args = sys.argv[2], sys.argv[3], json.loads(sys.argv[4])
        res = await session(role, lambda s: s.call_tool(tool, args))
        print("isError:", res.is_error)
        for c in res.content:
            print(getattr(c, "text", c))


asyncio.run(main())
