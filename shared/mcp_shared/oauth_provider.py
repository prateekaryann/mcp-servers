"""
In-memory OAuth 2.0 Authorization Server Provider for GitHub MCP Server.

Personal-use implementation: stores clients, tokens, and auth codes in memory.
The /authorize flow presents a simple password prompt — set MCP_AUTH_PASSWORD
env var (defaults to "approve").

All state is lost on restart, which is fine for personal tunneled use.
Claude.ai will just re-register and re-authorize.
"""

import os
import time
import secrets
import hashlib
from typing import Optional
from urllib.parse import urlencode

from mcp.server.auth.provider import (
    OAuthAuthorizationServerProvider,
    AuthorizationParams,
    AuthorizationCode,
    RefreshToken,
    AccessToken,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken


# Password to approve OAuth authorization (shown on consent page)
AUTH_PASSWORD = os.environ.get("MCP_AUTH_PASSWORD", "approve")


class InMemoryOAuthProvider:
    """
    In-memory OAuth provider for personal MCP server use.

    Implements the full OAuthAuthorizationServerProvider protocol:
    - Dynamic client registration (Claude.ai registers itself)
    - Authorization code flow with PKCE
    - Access/refresh token management
    - Token revocation
    """

    def __init__(self):
        # Storage (in-memory, lost on restart)
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._auth_codes: dict[str, AuthorizationCode] = {}
        self._access_tokens: dict[str, AccessToken] = {}
        self._refresh_tokens: dict[str, RefreshToken] = {}
        # Map auth codes to their PKCE params for the consent callback
        self._pending_auth: dict[str, dict] = {}

    async def get_client(self, client_id: str) -> Optional[OAuthClientInformationFull]:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self._clients[client_info.client_id] = client_info

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """
        Return URL to a consent page. For personal use, this is a simple
        HTML form that asks for the configured password.
        """
        # Generate a temporary request ID to track this auth flow
        request_id = secrets.token_urlsafe(16)

        # Store the pending authorization params
        self._pending_auth[request_id] = {
            "client_id": client.client_id,
            "redirect_uri": str(params.redirect_uri),
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
            "state": params.state,
            "scopes": params.scopes or [],
            "code_challenge": params.code_challenge,
            "resource": params.resource,
        }

        # Redirect to our consent endpoint
        return f"/consent?request_id={request_id}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> Optional[AuthorizationCode]:
        code = self._auth_codes.get(authorization_code)
        if code and code.client_id == client.client_id:
            if code.expires_at > time.time():
                return code
            # Expired — clean up
            del self._auth_codes[authorization_code]
        return None

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        # Remove used auth code (one-time use)
        self._auth_codes.pop(authorization_code.code, None)

        # Generate tokens
        access_token_str = secrets.token_urlsafe(32)
        refresh_token_str = secrets.token_urlsafe(32)

        access_token = AccessToken(
            token=access_token_str,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=int(time.time()) + 3600,  # 1 hour
            resource=authorization_code.resource,
        )
        refresh_token = RefreshToken(
            token=refresh_token_str,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
        )

        self._access_tokens[access_token_str] = access_token
        self._refresh_tokens[refresh_token_str] = refresh_token

        return OAuthToken(
            access_token=access_token_str,
            token_type="Bearer",
            expires_in=3600,
            refresh_token=refresh_token_str,
            scope=" ".join(authorization_code.scopes) if authorization_code.scopes else None,
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> Optional[RefreshToken]:
        token = self._refresh_tokens.get(refresh_token)
        if token and token.client_id == client.client_id:
            return token
        return None

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        # Revoke old refresh token
        self._refresh_tokens.pop(refresh_token.token, None)

        # Generate new tokens
        new_access = secrets.token_urlsafe(32)
        new_refresh = secrets.token_urlsafe(32)
        effective_scopes = scopes if scopes else refresh_token.scopes

        self._access_tokens[new_access] = AccessToken(
            token=new_access,
            client_id=client.client_id,
            scopes=effective_scopes,
            expires_at=int(time.time()) + 3600,
        )
        self._refresh_tokens[new_refresh] = RefreshToken(
            token=new_refresh,
            client_id=client.client_id,
            scopes=effective_scopes,
        )

        return OAuthToken(
            access_token=new_access,
            token_type="Bearer",
            expires_in=3600,
            refresh_token=new_refresh,
            scope=" ".join(effective_scopes) if effective_scopes else None,
        )

    async def load_access_token(self, token: str) -> Optional[AccessToken]:
        access = self._access_tokens.get(token)
        if access and (access.expires_at is None or access.expires_at > time.time()):
            return access
        if access:
            del self._access_tokens[token]
        return None

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        if isinstance(token, AccessToken):
            self._access_tokens.pop(token.token, None)
        elif isinstance(token, RefreshToken):
            self._refresh_tokens.pop(token.token, None)

    # -------------------------------------------------------------------------
    # Consent page helpers (called from server.py route)
    # -------------------------------------------------------------------------

    def get_pending_auth(self, request_id: str) -> Optional[dict]:
        return self._pending_auth.get(request_id)

    def complete_authorization(self, request_id: str) -> Optional[str]:
        """
        Complete the authorization flow: generate auth code and return redirect URL.
        Returns the redirect URL with code and state, or None if request_id is invalid.
        """
        pending = self._pending_auth.pop(request_id, None)
        if not pending:
            return None

        code = secrets.token_urlsafe(32)
        self._auth_codes[code] = AuthorizationCode(
            code=code,
            scopes=pending["scopes"],
            expires_at=time.time() + 300,  # 5 min expiry
            client_id=pending["client_id"],
            code_challenge=pending["code_challenge"],
            redirect_uri=pending["redirect_uri"],
            redirect_uri_provided_explicitly=pending["redirect_uri_provided_explicitly"],
            resource=pending.get("resource"),
        )

        return construct_redirect_uri(
            pending["redirect_uri"],
            code=code,
            state=pending.get("state"),
        )
