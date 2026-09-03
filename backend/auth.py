"""Supabase JWT verification.

Every route except /health requires a valid token. The frontend never talks to
Supabase directly and never holds the service key -- it authenticates with
Supabase Auth, then sends that JWT here.

The JWKS is cached at module scope so warm invocations do not refetch it.
"""

from __future__ import annotations

import os
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, Request, status
from jwt import PyJWKClient


@lru_cache(maxsize=1)
def _jwk_client() -> PyJWKClient:
    project_url = os.environ.get("SUPABASE_URL")
    if not project_url:
        raise RuntimeError("SUPABASE_URL is not set on the function.")
    return PyJWKClient(f"{project_url.rstrip('/')}/auth/v1/.well-known/jwks.json")


class User:
    def __init__(self, claims: dict) -> None:
        self.id: str = claims.get("sub", "")
        self.email: str | None = claims.get("email")
        self.claims = claims


def current_user(request: Request) -> User:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        signing_key = _jwk_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            # Asymmetric only. Never add HS256 here: mixing symmetric and
            # asymmetric algorithms is what enables JWT algorithm-confusion attacks.
            algorithms=["RS256", "ES256", "EdDSA"],
            audience="authenticated",
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired.")
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=f"Invalid token: {exc}")

    return User(claims)


RequireUser = Depends(current_user)
