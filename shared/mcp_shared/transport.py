"""MCP server transport abstraction.

Provides create_server() and run_server() — the two functions every
MCP server needs. Handles stdio vs SSE transport, OAuth setup,
consent page mounting, and uvicorn startup automatically.

Usage:
    from mcp_shared import create_server, run_server

    mcp = create_server("my-service")

    @mcp.tool()
    def my_tool(): ...

    if __name__ == "__main__":
        run_server(mcp)
"""

import os

from mcp.server.fastmcp import FastMCP

from mcp_shared.security import setup_logging


def create_server(name: str) -> FastMCP:
    """Create an MCP server with transport configured from environment.

    For stdio (default): returns a plain FastMCP instance.
    For SSE: configures OAuth 2.0 with dynamic client registration,
    authorization code flow (PKCE), and consent page.

    Args:
        name: Server name (e.g., "github", "slack", "jira").
              Used in logs, OAuth metadata, and the consent page.

    Returns:
        A FastMCP instance ready for @mcp.tool() registration.

    Environment variables:
        MCP_TRANSPORT: "stdio" (default) or "sse"
        MCP_SERVER_URL: Public URL for OAuth metadata (required for SSE)
        MCP_AUTH_PASSWORD: Consent page password (default: "approve")
    """
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    logger = setup_logging(name)

    if transport == "sse":
        from mcp.server.transport_security import TransportSecuritySettings
        from mcp.server.auth.settings import (
            AuthSettings,
            ClientRegistrationOptions,
            RevocationOptions,
        )
        from mcp_shared.oauth_provider import InMemoryOAuthProvider

        server_url = os.environ.get("MCP_SERVER_URL", "http://localhost:8080")
        security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
        oauth_provider = InMemoryOAuthProvider()

        auth_settings = AuthSettings(
            issuer_url=server_url,
            resource_server_url=server_url,
            client_registration_options=ClientRegistrationOptions(
                enabled=True,
                valid_scopes=["read", "write"],
                default_scopes=["read", "write"],
            ),
            revocation_options=RevocationOptions(enabled=True),
            required_scopes=["read"],
        )

        mcp = FastMCP(
            name,
            transport_security=security,
            auth=auth_settings,
            auth_server_provider=oauth_provider,
        )
        # Stash provider so run_server() can mount the consent page
        mcp._oauth_provider = oauth_provider
        logger.info(f"Created server '{name}' with SSE+OAuth transport")
    else:
        mcp = FastMCP(name)
        mcp._oauth_provider = None
        logger.info(f"Created server '{name}' with stdio transport")

    return mcp


def run_server(mcp: FastMCP, default_port: int = 8080):
    """Run the MCP server.

    For stdio: calls mcp.run() (blocking, for Claude Desktop/Code).
    For SSE: starts uvicorn with OAuth consent page (for Claude.ai via tunnel).

    Args:
        mcp: The FastMCP instance from create_server().
        default_port: Port for SSE (overridden by MCP_PORT env var).
    """
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    logger = setup_logging(mcp.name)

    if transport == "sse":
        port = int(os.environ.get("MCP_PORT", str(default_port)))
        import uvicorn
        from mcp_shared.consent import create_consent_route

        sse_app = mcp.sse_app()

        # Mount consent page if OAuth is configured
        if mcp._oauth_provider is not None:
            consent_route = create_consent_route(mcp._oauth_provider, mcp.name)
            sse_app.routes.insert(0, consent_route)

        read_only = os.environ.get("READ_ONLY", "false").lower() == "true"
        print(f"MCP Server '{mcp.name}' running on http://0.0.0.0:{port}")
        print(f"  Endpoint: http://localhost:{port}/sse")
        print(f"  Read-only: {read_only}")
        uvicorn.run(sse_app, host="0.0.0.0", port=port, log_level="info")
    else:
        logger.info(f"Starting '{mcp.name}' in stdio mode")
        mcp.run()
