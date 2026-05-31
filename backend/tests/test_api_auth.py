from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from dynamicrunner.auth.jwt import JwtVerificationError, SupabaseJwtVerifier
from tests.auth_fixtures import TEST_AUDIENCE, TEST_ISSUER, TEST_UID, make_access_token


def test_healthz_returns_ok(client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_me_requires_bearer_token(client) -> None:
    response = client.get("/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing bearer token"


def test_me_rejects_invalid_token(client) -> None:
    response = client.get("/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"


def test_me_accepts_valid_supabase_jwt(client, rsa_keys) -> None:
    private_pem, _ = rsa_keys
    token = make_access_token(private_pem)
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"uid": TEST_UID}


def test_me_rejects_expired_token(client, rsa_keys) -> None:
    private_pem, _ = rsa_keys
    token = make_access_token(private_pem, exp_delta=timedelta(hours=-1))
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_me_rejects_wrong_audience(client, rsa_keys) -> None:
    private_pem, _ = rsa_keys
    token = make_access_token(private_pem, audience="wrong-audience")
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_jwt_verifier_rejects_missing_sub(rsa_keys) -> None:
    private_pem, public_pem = rsa_keys
    now = datetime.now(tz=UTC)
    token = jwt.encode(
        {
            "aud": TEST_AUDIENCE,
            "iss": TEST_ISSUER,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        },
        private_pem,
        algorithm="RS256",
    )
    verifier = SupabaseJwtVerifier.from_static_key(
        issuer=TEST_ISSUER,
        audience=TEST_AUDIENCE,
        key=public_pem,
    )
    with pytest.raises(JwtVerificationError, match="sub"):
        verifier.verify(token)
