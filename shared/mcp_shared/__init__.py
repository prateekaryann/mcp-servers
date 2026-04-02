"""Shared infrastructure for MCP server collection.

Provides transport abstraction, OAuth, security, and CLI runner
so each MCP server only needs to define its tools.
"""

from mcp_shared.transport import create_server, run_server
from mcp_shared.runner import run_cli
from mcp_shared.security import (
    WORK_DIR,
    READ_ONLY,
    validate_path,
    log_tool_call,
    require_write_access,
)

__all__ = [
    "create_server",
    "run_server",
    "run_cli",
    "WORK_DIR",
    "READ_ONLY",
    "validate_path",
    "log_tool_call",
    "require_write_access",
]
