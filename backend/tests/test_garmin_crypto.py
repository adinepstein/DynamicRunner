"""Tests for crypto module and GarminCredentialStore."""

from __future__ import annotations

import json

import pytest

from dynamicrunner.crypto import EncryptionError, decrypt, encrypt, generate_key
from dynamicrunner.garmin import GarminTokens


class TestCrypto:
    def test_encrypt_decrypt_roundtrip(self) -> None:
        key = generate_key()
        plaintext = b"hello garmin tokens"
        ciphertext = encrypt(plaintext, key=key)
        assert ciphertext != plaintext
        assert decrypt(ciphertext, key=key) == plaintext

    def test_decrypt_wrong_key_raises(self) -> None:
        key1 = generate_key()
        key2 = generate_key()
        ciphertext = encrypt(b"secret", key=key1)
        with pytest.raises(EncryptionError, match="wrong key"):
            decrypt(ciphertext, key=key2)

    def test_encrypt_invalid_key_raises(self) -> None:
        with pytest.raises(EncryptionError, match="Invalid encryption key"):
            encrypt(b"data", key="not-a-valid-fernet-key")

    def test_decrypt_corrupted_data_raises(self) -> None:
        key = generate_key()
        with pytest.raises(EncryptionError, match="wrong key"):
            decrypt(b"corrupted-garbage", key=key)

    def test_generate_key_format(self) -> None:
        key = generate_key()
        assert len(key) == 44
        assert key.endswith("=")

    def test_json_token_roundtrip(self) -> None:
        key = generate_key()
        token_data = {
            "oauth1_token": "abc123",
            "oauth1_token_secret": "secret456",
            "extra_field": "value",
        }
        plaintext = json.dumps(token_data).encode()
        ciphertext = encrypt(plaintext, key=key)
        recovered = json.loads(decrypt(ciphertext, key=key))
        assert recovered == token_data


class TestGarminTokens:
    def test_to_from_json_bytes(self) -> None:
        raw = {"oauth1_token": "t1", "oauth1_token_secret": "s1", "domain": "garmin.com"}
        tokens = GarminTokens(oauth1_token="t1", oauth1_token_secret="s1", raw=raw)
        data = tokens.to_json_bytes()
        recovered = GarminTokens.from_json_bytes(data)
        assert recovered.oauth1_token == "t1"
        assert recovered.oauth1_token_secret == "s1"
        assert recovered.raw == raw

    def test_from_json_missing_fields(self) -> None:
        raw = {"some_other_format": True}
        tokens = GarminTokens.from_json_bytes(json.dumps(raw).encode())
        assert tokens.oauth1_token == ""
        assert tokens.oauth1_token_secret == ""
        assert tokens.raw == raw
