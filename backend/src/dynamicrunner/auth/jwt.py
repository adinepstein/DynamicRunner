from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient, PyJWKClientError


class JwtVerificationError(Exception):
    """Raised when a bearer token fails validation."""


@dataclass(frozen=True)
class VerifiedToken:
    sub: str
    claims: dict[str, Any]


class SupabaseJwtVerifier:
    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks_client: PyJWKClient | None = None,
        static_key: str | bytes | None = None,
        algorithms: tuple[str, ...] = ("RS256", "ES256", "HS256"),
    ) -> None:
        if jwks_client is None and static_key is None:
            raise ValueError("Either jwks_client or static_key is required")
        self._issuer = issuer
        self._audience = audience
        self._jwks_client = jwks_client
        self._static_key = static_key
        self._algorithms = algorithms

    @classmethod
    def from_supabase_url(
        cls,
        supabase_url: str,
        *,
        audience: str = "authenticated",
    ) -> SupabaseJwtVerifier:
        issuer = f"{supabase_url.rstrip('/')}/auth/v1"
        jwks_url = f"{issuer}/.well-known/jwks.json"
        return cls(issuer=issuer, audience=audience, jwks_client=PyJWKClient(jwks_url))

    @classmethod
    def from_static_key(
        cls,
        *,
        issuer: str,
        audience: str,
        key: str | bytes,
        algorithms: tuple[str, ...] = ("RS256",),
    ) -> SupabaseJwtVerifier:
        return cls(issuer=issuer, audience=audience, static_key=key, algorithms=algorithms)

    def verify(self, token: str) -> VerifiedToken:
        try:
            if self._static_key is not None:
                signing_key: str | bytes = self._static_key
            else:
                assert self._jwks_client is not None
                signing_key = self._jwks_client.get_signing_key_from_jwt(token).key

            claims = jwt.decode(
                token,
                signing_key,
                algorithms=list(self._algorithms),
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "sub"]},
            )
        except PyJWKClientError as exc:
            raise JwtVerificationError("Unable to resolve signing key") from exc
        except jwt.PyJWTError as exc:
            raise JwtVerificationError(str(exc)) from exc

        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub:
            raise JwtVerificationError("Token missing sub claim")

        return VerifiedToken(sub=sub, claims=claims)
