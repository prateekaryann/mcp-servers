#!/usr/bin/env python3
"""
[Your Server Name] MCP Server

An MCP server that provides [description] operations for Claude.

Prerequisites:
    1. Install [required CLI tool]: [url]
    2. Authenticate: [auth command]

Usage:
    python server.py
"""

from mcp_shared import (
    create_server,
    run_server,
    run_cli,
    log_tool_call,
    require_write_access,
)

# Create the MCP server (transport configured via MCP_TRANSPORT env var)
mcp = create_server("your-server-name")


# =============================================================================
# CLI HELPER
# =============================================================================

def run_your_cli(args: list[str], cwd: str = None) -> dict:
    """Run your CLI tool. Returns {success, output, error}."""
    return run_cli("your-tool", args, cwd=cwd, timeout=60)


# =============================================================================
# TOOLS — Add your @mcp.tool() functions below
# =============================================================================

@mcp.tool()
def example_tool(query: str) -> str:
    """
    Example tool — replace with your actual tools.

    Args:
        query: What to search for

    Returns:
        Results or error message
    """
    log_tool_call("example_tool", query=query)

    result = run_your_cli(["search", query])

    if result["success"]:
        return f"Results:\n\n{result['output']}"
    else:
        return f"Error: {result['error']}"


# =============================================================================
# RUN SERVER
# =============================================================================

if __name__ == "__main__":
    run_server(mcp)
