# Architecture Guide

## Design Principles

### Domain-Driven Design (DDD)

Each MCP server is a **bounded context** — it owns its models, adapters, and business logic. No server reaches into another's internals.

```
mcp-servers/
├── shared/mcp_shared/    ← Shared Kernel (infrastructure all domains need)
├── servers/github/        ← GitHub Bounded Context
├── servers/freelance/     ← Freelance Bounded Context
└── servers/_template/     ← Scaffold for new contexts
```

### Separation of Concerns

```
┌─────────────────────────────────────────────────────────┐
│                    Your Server Code                      │
│  @mcp.tool() functions + domain helpers + validators     │
├─────────────────────────────────────────────────────────┤
│                    mcp_shared                            │
│  Transport │ Security │ OAuth │ CLI Runner │ Logging     │
├─────────────────────────────────────────────────────────┤
│                    MCP SDK (mcp[cli])                     │
│  FastMCP │ SSE │ Protocol │ Starlette │ uvicorn          │
└─────────────────────────────────────────────────────────┘
```

### Inversion of Control

Servers don't manage their lifecycle. They declare tools and call `run_server()`. The framework handles everything else: transport negotiation, OAuth flow, audit logging, signal handling.

---

## Shared Package: `mcp_shared`

| Module | Responsibility | Key Exports |
|--------|---------------|-------------|
| `transport.py` | Server lifecycle | `create_server()`, `run_server()` |
| `security.py` | Auth & validation | `validate_path()`, `log_tool_call()`, `require_write_access()` |
| `runner.py` | Subprocess execution | `run_cli()` |
| `oauth_provider.py` | OAuth 2.0 AS | `InMemoryOAuthProvider` |
| `consent.py` | Consent UI | `create_consent_route()` |

### Data Flow

```
Claude (Desktop/Code/Web)
  │
  ├── stdio ──→ FastMCP.run() ──→ Tool function ──→ run_cli("gh", [...])
  │                                                        │
  └── SSE ──→ OAuth handshake ──→ Authenticated SSE ──→ Tool function
              │                                            │
              ├── /.well-known/oauth-*  (auto)            └── run_cli(...)
              ├── /register             (auto)                    │
              ├── /authorize → /consent (password)               ↓
              └── /token                (auto)            CLI subprocess
                                                          (gh, git, curl, etc.)
```

---

## Server Structure (Domain Bounded Context)

Each server follows this pattern:

```
servers/your-service/
├── server.py          # Entry point: create_server + tools + run_server
├── adapters/          # (optional) External service adapters
│   ├── __init__.py    # Aggregator / registry
│   └── platform.py    # Per-platform adapter
├── models/            # (optional) Pydantic data models
├── matching/          # (optional) Business logic
├── notifications/     # (optional) Alert integrations
├── config.py          # (optional) Default configuration
├── .env.example       # Environment variables
└── README.md          # Server-specific docs
```

### Minimal Server (CLI wrapper like GitHub)

```python
from mcp_shared import create_server, run_server, run_cli, log_tool_call
mcp = create_server("my-service")

@mcp.tool()
def my_tool(query: str) -> str:
    log_tool_call("my_tool", query=query)
    return run_cli("my-cli", ["search", query])["output"]

if __name__ == "__main__":
    run_server(mcp)
```

### Complex Server (Adapter pattern like Freelance)

```python
from mcp_shared import create_server, run_server, log_tool_call
from adapters import Aggregator        # Domain-specific
from models import SearchParams        # Domain-specific
from matching import Scorer            # Domain-specific
mcp = create_server("freelance-jobs")

@mcp.tool()
async def search_jobs(keywords: list[str]) -> str:
    log_tool_call("search_jobs", keywords=str(keywords))
    aggregator = Aggregator()
    jobs = await aggregator.search(SearchParams(keywords=keywords))
    return format_results(jobs)

if __name__ == "__main__":
    run_server(mcp)
```

---

## Security Model

| Layer | What | Where |
|-------|------|-------|
| **Path sandboxing** | All file paths constrained to WORK_DIR | `security.py:validate_path()` |
| **Input validation** | Regex checks on user-provided strings | Per-server validators |
| **Read-only mode** | Blocks all write tools | `security.py:require_write_access()` |
| **Audit logging** | Every tool call logged | `security.py:log_tool_call()` |
| **OAuth 2.0** | Token-based auth for remote access | `oauth_provider.py` + `consent.py` |
| **Subprocess isolation** | No shell=True, list-based args | `runner.py:run_cli()` |

---

## Transport Modes

| Mode | Use Case | Auth | Config |
|------|----------|------|--------|
| **stdio** | Claude Desktop, Claude Code | None needed (local) | `MCP_TRANSPORT=stdio` (default) |
| **SSE** | Claude.ai via tunnel | OAuth 2.0 | `MCP_TRANSPORT=sse` + `MCP_SERVER_URL` |

Both modes use the exact same tool functions. Transport is invisible to tool code.
