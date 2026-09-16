"""
MCP client wrapper for the Python-exec tool. Spawns `mcp_server/python_exec_server.py`
as a subprocess over stdio transport and calls its `run_python_exec_tool` tool,
matching the MCP framing everywhere else in this project treats "python_exec" as a
tool rather than a plain function call.

`coder_agent.py` calls `run_python_exec_via_mcp(...)` (async) by default. If spawning
the MCP server fails for any reason (e.g. the `mcp` package isn't installed in a given
environment), the caller falls back to the direct in-process call in
`tools/python_exec_tool.py` — same contract, so callers don't need to care which path
ran.
"""
import json
import sys
import os
from contextlib import AsyncExitStack

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from tools.logger import log_event

_SERVER_MODULE = "mcp_server.python_exec_server"


async def run_python_exec_via_mcp(
    code: str,
    input_paths: dict,
    output_path: str,
    timeout: int = 60,
    run_id: str = None,
) -> dict:
    """Async MCP round-trip to the python-exec server. Returns the same
    {"success", "stdout", "stderr", "output_path"} shape as the direct call."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", _SERVER_MODULE],
        env=os.environ.copy(),
    )

    if run_id:
        log_event(run_id, "mcp_client", "spawn_server", server_module=_SERVER_MODULE)

    async with AsyncExitStack() as stack:
        read, write = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()

        result = await session.call_tool(
            "run_python_exec_tool",
            arguments={
                "code": code, "input_paths": input_paths, "output_path": output_path,
                "timeout": timeout, "run_id": run_id or "",
            },
        )

    if result.is_error:
        error_text = "; ".join(
            block.text for block in result.content if getattr(block, "text", None)
        )
        if run_id:
            log_event(run_id, "mcp_client", "call_failed", error=error_text)
        return {"success": False, "stdout": "", "stderr": error_text, "output_path": None}

    # FastMCP/MCPServer tools returning a dict come back as structured content when
    # available, otherwise as a JSON text block — handle both.
    if result.structured_content is not None:
        payload = result.structured_content
    else:
        text_block = next((b for b in result.content if getattr(b, "text", None)), None)
        payload = json.loads(text_block.text) if text_block else {
            "success": False, "stdout": "", "stderr": "empty MCP response", "output_path": None,
        }

    if run_id:
        log_event(run_id, "mcp_client", "call_succeeded", success=payload.get("success"))
    return payload
