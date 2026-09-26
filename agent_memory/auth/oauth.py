"""Google OAuth 2.0 Service using standard httpx."""

import httpx
from urllib.parse import urlencode
from typing import Optional, Dict, Any
from ..config import settings

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SCOPES = ["openid", "email", "profile"]


def get_google_auth_url(state: str, redirect_uri: Optional[str] = None) -> str:
    """Generate the Google sign-in redirect URL."""
    target_redirect_uri = redirect_uri or settings.google_redirect_uri
    if target_redirect_uri and not target_redirect_uri.startswith("http"):
        target_redirect_uri = f"{settings.app_base_url.rstrip('/')}/{target_redirect_uri.lstrip('/')}"

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": target_redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
        "include_granted_scopes": "true",
        "prompt": "consent",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def exchange_google_code(code: str, redirect_uri: Optional[str] = None) -> Dict[str, Any]:
    """Exchange authorization code for Google profile data using synchronous httpx Client."""
    # Build candidate redirect URIs in priority order
    candidate_uris = []
    if redirect_uri:
        uri = redirect_uri if redirect_uri.startswith("http") else f"{settings.app_base_url.rstrip('/')}/{redirect_uri.lstrip('/')}"
        if uri not in candidate_uris:
            candidate_uris.append(uri)

    default_uri = settings.google_redirect_uri
    if default_uri:
        uri = default_uri if default_uri.startswith("http") else f"{settings.app_base_url.rstrip('/')}/{default_uri.lstrip('/')}"
        if uri not in candidate_uris:
            candidate_uris.append(uri)

    base = settings.app_base_url.rstrip('/')
    for path in ["/landing", "/auth/google/callback", "/v1/auth/google/callback", "/api/v1/auth/google/callback"]:
        uri = f"{base}{path}"
        if uri not in candidate_uris:
            candidate_uris.append(uri)

    last_error = None
    with httpx.Client(timeout=15.0) as client:
        for uri in candidate_uris:
            token_res = client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code.strip(),
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": uri,
                    "grant_type": "authorization_code",
                },
            )
            if token_res.status_code == 200:
                access_token = token_res.json().get("access_token")
                userinfo_res = client.get(
                    GOOGLE_USERINFO_URL,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if userinfo_res.status_code == 200:
                    return userinfo_res.json()
                raise RuntimeError(f"Failed to fetch Google userinfo [{userinfo_res.status_code}]: {userinfo_res.text}")

            last_error = f"Google token error [{token_res.status_code}] with redirect_uri={uri}: {token_res.text}"
            # Only retry if failure was due to redirect_uri mismatch
            if "redirect_uri_mismatch" not in token_res.text:
                break

    raise RuntimeError(last_error or "Google OAuth code exchange failed.")

