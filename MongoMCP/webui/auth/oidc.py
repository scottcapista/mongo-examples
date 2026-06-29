"""OIDC Authorization Code + PKCE for the Web UI Flask server."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import jwt
import requests
from flask import redirect, session
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from jwt import PyJWKClient

from local_settings import settings

logger = logging.getLogger(__name__)

SESSION_USER_KEY = "oidc_user"
OIDC_STATE_MAX_AGE = 600


@dataclass
class UserSession:
    sub: str
    email: str
    display_name: str
    access_token: str
    id_token_claims: Dict[str, Any]


def is_oidc_configured() -> bool:
    return bool(
        getattr(settings, "OIDC_ISSUER", "")
        and getattr(settings, "OIDC_CLIENT_ID", "")
        and getattr(settings, "OIDC_REDIRECT_URI", "")
    )


def auth_required() -> bool:
    return bool(getattr(settings, "AUTH_REQUIRED", False))


@lru_cache(maxsize=4)
def _fetch_oidc_metadata(issuer: str) -> Dict[str, Any]:
    issuer = issuer.rstrip("/")
    url = f"{issuer}/.well-known/openid-configuration"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _signing_secret() -> str:
    secret = getattr(settings, "SESSION_SECRET", "") or ""
    if not secret:
        raise RuntimeError("SESSION_SECRET is required for OIDC login")
    return secret


def _state_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_signing_secret(), salt="oidc-pkce-state")


def _encode_oauth_state(nonce: str, verifier: str) -> str:
    return _state_serializer().dumps({"n": nonce, "v": verifier})


def _decode_oauth_state(state: str) -> tuple[str, str]:
    try:
        payload = _state_serializer().loads(state, max_age=OIDC_STATE_MAX_AGE)
    except SignatureExpired as exc:
        raise ValueError("OIDC state expired; try signing in again") from exc
    except BadSignature as exc:
        raise ValueError("Invalid OIDC state") from exc
    nonce = payload.get("n")
    verifier = payload.get("v")
    if not nonce or not verifier:
        raise ValueError("Invalid OIDC state payload")
    return nonce, verifier


def _claims_email(claims: Dict[str, Any]) -> str:
    return (
        claims.get("email")
        or claims.get("preferred_username")
        or claims.get("upn")
        or claims.get("sub")
        or ""
    )


def _claims_display_name(claims: Dict[str, Any], email: str) -> str:
    return claims.get("name") or claims.get("given_name") or email or claims.get("sub", "")


def _validate_id_token(id_token: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    jwks_uri = metadata["jwks_uri"]
    issuer = metadata["issuer"]
    client_id = settings.OIDC_CLIENT_ID
    jwks_client = PyJWKClient(jwks_uri)
    signing_key = jwks_client.get_signing_key_from_jwt(id_token)
    return jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256"],
        audience=client_id,
        issuer=issuer,
        options={"verify_at_hash": False},
    )


def start_login():
    """Redirect browser to IdP authorization endpoint (PKCE)."""
    if not is_oidc_configured():
        raise RuntimeError("OIDC is not configured (OIDC_ISSUER, OIDC_CLIENT_ID, OIDC_REDIRECT_URI)")

    metadata = _fetch_oidc_metadata(settings.OIDC_ISSUER)
    nonce = secrets.token_urlsafe(32)
    verifier = _pkce_verifier()
    signed_state = _encode_oauth_state(nonce, verifier)

    params = {
        "response_type": "code",
        "client_id": settings.OIDC_CLIENT_ID,
        "redirect_uri": settings.OIDC_REDIRECT_URI,
        "scope": settings.OIDC_SCOPES,
        "state": signed_state,
        "code_challenge": _pkce_challenge(verifier),
        "code_challenge_method": "S256",
    }
    auth_url = f"{metadata['authorization_endpoint']}?{urlencode(params)}"
    return redirect(auth_url)


def handle_callback(code: str, state: str) -> UserSession:
    """Exchange authorization code for tokens and store user in Flask session."""
    _nonce, verifier = _decode_oauth_state(state)

    metadata = _fetch_oidc_metadata(settings.OIDC_ISSUER)
    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.OIDC_REDIRECT_URI,
        "client_id": settings.OIDC_CLIENT_ID,
        "code_verifier": verifier,
    }
    if getattr(settings, "OIDC_CLIENT_SECRET", ""):
        token_data["client_secret"] = settings.OIDC_CLIENT_SECRET

    resp = requests.post(
        metadata["token_endpoint"],
        data=token_data,
        headers={"Accept": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    tokens = resp.json()

    id_token = tokens.get("id_token")
    if not id_token:
        raise ValueError("Token response missing id_token")

    claims = _validate_id_token(id_token, metadata)
    email = _claims_email(claims)
    user = UserSession(
        sub=str(claims.get("sub", "")),
        email=email,
        display_name=_claims_display_name(claims, email),
        access_token=tokens.get("access_token", ""),
        id_token_claims=claims,
    )
    session[SESSION_USER_KEY] = {
        "sub": user.sub,
        "email": user.email,
        "display_name": user.display_name,
        "access_token": user.access_token,
        "id_token_claims": user.id_token_claims,
    }
    session.modified = True
    return user


def get_user_from_session() -> Optional[UserSession]:
    raw = session.get(SESSION_USER_KEY)
    if not raw:
        return None
    return UserSession(
        sub=raw["sub"],
        email=raw["email"],
        display_name=raw.get("display_name") or raw["email"],
        access_token=raw.get("access_token", ""),
        id_token_claims=raw.get("id_token_claims") or {},
    )


def clear_user_session() -> None:
    session.pop(SESSION_USER_KEY, None)


def user_session_to_dict(user: UserSession) -> Dict[str, str]:
    return {
        "sub": user.sub,
        "email": user.email,
        "display_name": user.display_name,
    }


def auth_required_response():
    """Return (json_body, status_code) when auth is required but missing."""
    return {"error": "Authentication required"}, 401


def resolve_query_identity(payload: Dict[str, Any]) -> tuple[Optional[str], Optional[str], Optional[tuple]]:
    """
    Return (user_id, username, error_response) for /query handlers.
    error_response is (body_dict, status_code) when request must be rejected.
    """
    user = get_user_from_session()
    if auth_required() and not user:
        err = auth_required_response()
        return None, None, err
    user_id = user.sub if user else payload.get("user_id")
    username = user.email if user else payload.get("username")
    return user_id, username, None
