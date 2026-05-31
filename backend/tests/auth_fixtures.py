from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

TEST_SUPABASE_URL = "https://test-project.supabase.co"
TEST_ISSUER = f"{TEST_SUPABASE_URL}/auth/v1"
TEST_AUDIENCE = "authenticated"
TEST_UID = "11111111-1111-1111-1111-111111111111"


def make_access_token(
    private_pem: bytes,
    *,
    sub: str = TEST_UID,
    exp_delta: timedelta = timedelta(hours=1),
    audience: str = TEST_AUDIENCE,
    issuer: str = TEST_ISSUER,
) -> str:
    now = datetime.now(tz=UTC)
    payload = {
        "sub": sub,
        "aud": audience,
        "iss": issuer,
        "iat": int(now.timestamp()),
        "exp": int((now + exp_delta).timestamp()),
        "role": "authenticated",
    }
    return jwt.encode(payload, private_pem, algorithm="RS256")
