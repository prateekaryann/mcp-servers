# Adding a New MCP Server

## Step-by-Step

### 1. Copy the template

```bash
cp -r servers/_template servers/your-service
```

### 2. Edit `servers/your-service/server.py`

```python
from mcp_shared import create_server, run_server, run_cli, log_tool_call

mcp = create_server("your-service")

def run_your_cli(args, cwd=None):
    return run_cli("your-tool", args, cwd=cwd)

@mcp.tool()
def your_first_tool(query: str) -> str:
    """What this tool does."""
    log_tool_call("your_first_tool", query=query)
    result = run_your_cli(["search", query])
    return result["output"] if result["success"] else f"Error: {result['error']}"

if __name__ == "__main__":
    run_server(mcp)
```

### 3. Test locally

```bash
pip install -e ./shared  # Once, from monorepo root
python servers/your-service/server.py
```

### 4. Add to Claude Desktop

```json
{
  "mcpServers": {
    "your-service": {
      "command": "python",
      "args": ["/path/to/mcp-servers/servers/your-service/server.py"]
    }
  }
}
```

### 5. Update docs
- Add a row to the servers table in root `README.md`
- Create `servers/your-service/README.md`

---

## Tool Implementation Checklist

Every tool should:

- [ ] Start with `log_tool_call("tool_name", param=value)`
- [ ] Call `require_write_access("tool_name")` if it modifies state
- [ ] Call `validate_path(path)` for any file system paths
- [ ] Validate user inputs (regex for names, IDs, etc.)
- [ ] Return user-friendly error messages (never raw exceptions)
- [ ] Have a clear docstring (shown to Claude as the tool description)

## Complex Server Pattern

For servers with multiple data sources (like the freelance server):

```
servers/your-service/
├── server.py          # Tools + run_server()
├── adapters/          # One file per external service
│   ├── __init__.py    # Aggregator that queries all adapters
│   ├── service_a.py
│   └── service_b.py
├── models/            # Pydantic models for your domain
│   └── __init__.py
├── config.py          # Default configuration
└── .env.example
```
