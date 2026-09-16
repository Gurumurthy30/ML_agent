"""
Real MCP server for the Python-exec tool.

This replaces the "placeholder for what will eventually be a real MCP server" note in
`tools/python_exec_tool.py` — the exec logic itself (subprocess, path-in/path-out,
INPUT_<KEY>/OUTPUT_PATH convention) is unchanged and still lives there; this file just
exposes it over the actual Model Context Protocol (stdio transport) instead of being
called as a plain Python function.

Run standalone for manual testing:
    python -m mcp_server.python_exec_server
Agents talk to it via tools/mcp_client.py, which spawns this file as a subprocess.
"""
from mcp.server.mcpserver import MCPServer

from tools.python_exec_tool import run_python_exec

server = MCPServer(
    name="python-exec",
    instructions=(
        "Executes a self-contained Python script in a subprocess. The script must "
        "read inputs from paths given via INPUT_<KEY> environment variables and "
        "write its primary result to the path in OUTPUT_PATH. No sandboxing yet — "
        "this is a placeholder-grade exec tool, not a hardened one."
    ),
)


@server.tool()
def run_python_exec_tool(
    code: str,
    input_paths: dict,
    output_path: str,
    timeout: int = 60,
    run_id: str = "",
) -> dict:
    """Run a Python script in a subprocess with path-in/path-out I/O.

    Args:
        code: Complete, self-contained Python source to execute.
        input_paths: Maps logical input names to file paths, exposed to the script
            as INPUT_<NAME> environment variables (name uppercased).
        output_path: Path the script must write its primary result to; also passed
            as the OUTPUT_PATH environment variable.
        timeout: Seconds to allow the subprocess to run before killing it.
        run_id: Optional run identifier, used only for local log correlation.

    Returns:
        {"success": bool, "stdout": str, "stderr": str, "output_path": str|None}
    """
    return run_python_exec(
        code=code, input_paths=input_paths, output_path=output_path,
        timeout=timeout, run_id=run_id or None, agent="python_exec_mcp_server",
    )


if __name__ == "__main__":
    server.run(transport="stdio")
