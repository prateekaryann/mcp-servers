# MCP Server Collection

A monorepo of **Model Context Protocol (MCP)** servers that give Claude access to external tools and services.

Each server wraps a CLI tool or API, exposing its capabilities as MCP tools. Shared infrastructure handles transport (stdio + SSE), OAuth 2.0 authentication, security, and audit logging — so each server only needs to define its tools.

## Servers

| Server | Tools | CLI | Description |
|--------|-------|-----|-------------|
| [GitHub](servers/github/) | 40 | `gh` | Repos, issues, PRs, branches, workflows, releases |
| [Freelance Jobs](servers/freelance/) | 7 | `httpx` | Search 8 job platforms, skill matching, notifications |
| *More coming...* | | | Slack, Calendar, AWS, etc. |

## Architecture

```
mcp-servers/
├── shared/              # Shared Python package (mcp-shared)
│   └── mcp_shared/      # Transport, OAuth, security, subprocess runner
├── servers/
│   ├── github/          # GitHub MCP server (40 tools)
│   └── _template/       # Copy this to create a new server
├── tunnel.sh            # Start any server + ngrok tunnel
└── tunnel.ps1           # PowerShell version
```

## Quick Start

```bash
# 1. Clone
git clone https://github.com/prateekaryann/mcp-servers.git
cd mcp-servers

# 2. Install shared package (editable — changes take effect immediately)
pip install -e ./shared

# 3. Run a server (local, for Claude Desktop/Code)
python servers/github/server.py

# 4. Or run remotely (for Claude.ai, with OAuth)
MCP_TRANSPORT=sse MCP_PORT=9000 MCP_SERVER_URL=https://your-tunnel.ngrok-free.dev python servers/github/server.py
```

## Creating a New Server

```bash
# 1. Copy the template
cp -r servers/_template servers/your-service

# 2. Edit servers/your-service/server.py — add your tools
# 3. Run it
python servers/your-service/server.py
```

The template gives you ~20 lines of boilerplate. Everything else — transport, OAuth, logging, security — is handled by `mcp_shared`.

## Shared Infrastructure (`mcp_shared`)

Every server gets these for free:

| Feature | Description |
|---------|-------------|
| **Transport** | stdio (local) or SSE (remote) — configured via `MCP_TRANSPORT` env var |
| **OAuth 2.0** | Auto-configured for SSE — dynamic client registration, PKCE, consent page |
| **Security** | Path sandboxing, audit logging, read-only mode |
| **CLI Runner** | `run_cli(command, args)` — universal subprocess wrapper |

### Key Functions

```python
from mcp_shared import create_server, run_server, run_cli, log_tool_call, require_write_access

mcp = create_server("my-service")  # Handles transport + OAuth setup

@mcp.tool()
def my_tool(query: str) -> str:
    log_tool_call("my_tool", query=query)
    result = run_cli("my-cli", ["search", query])
    return result["output"] if result["success"] else f"Error: {result['error']}"

if __name__ == "__main__":
    run_server(mcp)  # Handles stdio/SSE/uvicorn
```

## Configuration

All servers share these environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_TRANSPORT` | `stdio` | `stdio` (local) or `sse` (remote) |
| `MCP_PORT` | `8080` | Port for SSE transport |
| `MCP_SERVER_URL` | `http://localhost:8080` | Public URL for OAuth metadata |
| `MCP_AUTH_PASSWORD` | `approve` | OAuth consent page password |
| `WORK_DIR` | `~/projects` | Sandbox directory for file operations |
| `READ_ONLY` | `false` | Block all write tools when `true` |
| `LOG_FILE` | `mcp_audit.log` | Audit log file path |

## Claude Desktop Configuration

```json
{
  "mcpServers": {
    "github": {
      "command": "python",
      "args": ["/path/to/mcp-servers/servers/github/server.py"]
    }
  }
}
```

## Author

**Prateek Aryan** — [@prateekaryann](https://github.com/prateekaryann)

## License

MIT
