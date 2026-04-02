"""Generic CLI subprocess runner for MCP servers.

Every MCP server wraps a CLI tool (gh, git, slack, aws, etc.).
This module provides a universal subprocess pattern that each server
customizes with a thin wrapper.

Example:
    def run_gh(args, cwd=None):
        return run_cli("gh", args, cwd=cwd, timeout=60)
"""

import subprocess
from typing import Optional


def run_cli(
    command: str,
    args: list[str],
    cwd: Optional[str] = None,
    timeout: int = 60,
) -> dict:
    """
    Run a CLI command and return the result.

    Args:
        command: The CLI tool to run (e.g., "gh", "git", "slack", "aws")
        args: Arguments to pass to the command
        cwd: Working directory (default: current directory)
        timeout: Command timeout in seconds (default: 60)

    Returns:
        Dict with 'success' (bool), 'output' (str), and 'error' (str|None)
    """
    try:
        result = subprocess.run(
            [command] + args,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout.strip(),
            "error": result.stderr.strip() if result.returncode != 0 else None,
        }
    except FileNotFoundError:
        return {
            "success": False,
            "output": "",
            "error": f"'{command}' not found. Make sure it's installed and in PATH.",
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": "",
            "error": f"Command timed out after {timeout} seconds",
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
        }
