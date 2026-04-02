"""Security infrastructure for MCP servers.

Provides path sandboxing, audit logging, and read-only mode.
All MCP servers should use these in their tool implementations:

    @mcp.tool()
    def my_tool(repo_path: str) -> str:
        log_tool_call("my_tool", repo_path=repo_path)
        try:
            require_write_access("my_tool")
            repo_path = validate_path(repo_path)
        except (PermissionError, ValueError) as e:
            return str(e)
        # ... tool logic ...
"""

import os
import sys
import logging
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration (from environment)
# ---------------------------------------------------------------------------

WORK_DIR = Path(os.environ.get("WORK_DIR", str(Path.home() / "projects")))

READ_ONLY = os.environ.get("READ_ONLY", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_logging_configured = False


def setup_logging(server_name: str = "mcp") -> logging.Logger:
    """Configure audit logging. Safe to call multiple times."""
    global _logging_configured
    if not _logging_configured:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[
                logging.StreamHandler(sys.stderr),
                logging.FileHandler(os.environ.get("LOG_FILE", "mcp_audit.log")),
            ],
        )
        _logging_configured = True
    return logging.getLogger(server_name)


logger = setup_logging()

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def validate_path(path: str) -> str:
    """Validate and sandbox a path to WORK_DIR.

    Prevents directory traversal by ensuring the resolved path
    is inside WORK_DIR. Uses os.sep suffix check to prevent
    prefix-matching bypass (e.g., /home/user/pro vs /home/user/projects-evil).

    Raises:
        ValueError: If path is outside WORK_DIR.
    """
    resolved = Path(path).expanduser().resolve()
    work_resolved = WORK_DIR.resolve()
    if resolved != work_resolved and not str(resolved).startswith(str(work_resolved) + os.sep):
        raise ValueError(
            f"Path '{path}' is outside allowed directory '{WORK_DIR}'. "
            f"Set WORK_DIR env var to change the allowed base directory."
        )
    return str(resolved)


def log_tool_call(tool_name: str, **kwargs):
    """Log every tool invocation for audit trail.

    Truncates long string values to prevent log bloat.
    """
    safe_kwargs = {
        k: (v[:100] + "..." if isinstance(v, str) and len(v) > 100 else v)
        for k, v in kwargs.items()
    }
    logger.info(f"TOOL_CALL: {tool_name} | params={safe_kwargs}")


def require_write_access(tool_name: str):
    """Block write operations when READ_ONLY mode is enabled.

    Raises:
        PermissionError: If READ_ONLY=true.
    """
    if READ_ONLY:
        raise PermissionError(
            f"Tool '{tool_name}' is blocked in READ_ONLY mode. "
            f"Set READ_ONLY=false to enable write operations."
        )
