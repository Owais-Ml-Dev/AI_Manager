"""Verifies Supabase Auth access tokens (JWT, ES256) via Supabase's public JWKS.

We never issue or store passwords ourselves — Supabase Auth owns signup/login
entirely. This only verifies the token Supabase already issued and extracts
the user id (the `sub` claim) for ownership checks.
"""
import jwt
from fastapi import Header, HTTPException
from jwt import PyJWKClient

from app.core.config import settings

_jwks_client = PyJWKClient(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json")


async def get_current_user_id(authorization: str = Header(default="")) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        # leeway tolerates ordinary clock drift between this server and
        # Supabase's (observed: tens of milliseconds) on the iat/exp checks.
        payload = jwt.decode(
            token, signing_key.key, algorithms=["ES256"], audience="authenticated", leeway=10
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing subject claim")
    return user_id
