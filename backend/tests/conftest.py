from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from dynamicrunner.api.app import create_app
from dynamicrunner.auth.jwt import SupabaseJwtVerifier
from dynamicrunner.config import Settings
from tests.auth_fixtures import TEST_AUDIENCE, TEST_ISSUER, TEST_SUPABASE_URL


@pytest.fixture(scope="session")
def rsa_keys() -> tuple[bytes, bytes]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


@pytest.fixture
def test_verifier(rsa_keys: tuple[bytes, bytes]) -> SupabaseJwtVerifier:
    _, public_pem = rsa_keys
    return SupabaseJwtVerifier.from_static_key(
        issuer=TEST_ISSUER,
        audience=TEST_AUDIENCE,
        key=public_pem,
    )


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        supabase_url=TEST_SUPABASE_URL,
        supabase_jwt_audience=TEST_AUDIENCE,
        log_level="WARNING",
    )


@pytest.fixture
def client(test_settings: Settings, test_verifier: SupabaseJwtVerifier) -> TestClient:
    app = create_app(
        settings=test_settings,
        verifier_factory=lambda: test_verifier,
    )
    return TestClient(app)
