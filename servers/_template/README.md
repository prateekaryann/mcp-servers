# [Server Name] MCP Server

An MCP server that provides [description] operations for Claude.

## Prerequisites

- Python 3.10+
- [Required CLI tool]

## Quick Start

```bash
# Install shared package (from monorepo root, once)
pip install -e ./shared

# Run the server
cd servers/your-server
python server.py
```

## Tools

| Tool | Description |
|------|-------------|
| `example_tool` | Example — replace with your tools |

## Remote Access (Claude.ai)

```bash
MCP_TRANSPORT=sse MCP_PORT=9000 MCP_SERVER_URL=https://your-tunnel.ngrok-free.dev python server.py
```
