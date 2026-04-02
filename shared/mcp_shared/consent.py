"""OAuth consent page for MCP servers.

Provides a simple password-based consent flow for personal use.
Shown when a client (like Claude.ai) tries to authorize via OAuth.
"""

import os
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route


AUTH_PASSWORD = os.environ.get("MCP_AUTH_PASSWORD", "approve")


def create_consent_route(oauth_provider, server_name: str = "MCP Server") -> Route:
    """Create a Starlette route for the OAuth consent page.

    Args:
        oauth_provider: An InMemoryOAuthProvider instance
        server_name: Display name shown on the consent page

    Returns:
        A Starlette Route handling GET/POST at /consent
    """

    async def consent_page(request: Request):
        request_id = request.query_params.get("request_id", "")
        error = request.query_params.get("error", "")

        if request.method == "POST":
            form = await request.form()
            password = form.get("password", "")
            req_id = form.get("request_id", "")

            if password == AUTH_PASSWORD:
                redirect_url = oauth_provider.complete_authorization(req_id)
                if redirect_url:
                    return RedirectResponse(redirect_url, status_code=302)
                return HTMLResponse(
                    "<h2>Invalid or expired request</h2>", status_code=400
                )
            else:
                return RedirectResponse(
                    f"/consent?request_id={req_id}&error=wrong_password",
                    status_code=302,
                )

        pending = oauth_provider.get_pending_auth(request_id)
        if not pending:
            return HTMLResponse(
                "<h2>Invalid or expired authorization request</h2>",
                status_code=400,
            )

        error_html = (
            '<p style="color:red">Wrong password. Try again.</p>' if error else ""
        )

        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html><head><title>{server_name} - Authorize</title>
        <style>
            body {{ font-family: -apple-system, sans-serif; max-width: 400px; margin: 80px auto; padding: 20px; }}
            h2 {{ color: #333; }}
            .info {{ background: #f0f0f0; padding: 12px; border-radius: 8px; margin: 16px 0; font-size: 14px; }}
            input[type=password] {{ width: 100%; padding: 10px; margin: 8px 0; border: 1px solid #ccc; border-radius: 4px; font-size: 16px; }}
            button {{ width: 100%; padding: 12px; background: #2563eb; color: white; border: none; border-radius: 4px; font-size: 16px; cursor: pointer; }}
            button:hover {{ background: #1d4ed8; }}
        </style></head>
        <body>
            <h2>Authorize {server_name}</h2>
            <div class="info">
                <strong>Client:</strong> {pending['client_id'][:16]}...<br>
                <strong>Scopes:</strong> {', '.join(pending.get('scopes', ['read', 'write']))}
            </div>
            {error_html}
            <form method="POST" action="/consent">
                <input type="hidden" name="request_id" value="{request_id}">
                <label>Enter password to approve:</label>
                <input type="password" name="password" autofocus placeholder="Password">
                <br><br>
                <button type="submit">Approve Connection</button>
            </form>
        </body></html>
        """)

    return Route("/consent", consent_page, methods=["GET", "POST"])
