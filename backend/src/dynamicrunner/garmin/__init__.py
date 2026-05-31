"""Garmin credential storage — encrypt/decrypt token blobs in Postgres.

Uses service role to read/write `garmin_credentials` (no RLS policies for
authenticated users — this table is server-only).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from dynamicrunner.config import Settings
from dynamicrunner.crypto import EncryptionError, decrypt, encrypt

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class GarminTokens:
    """Deserialized Garmin OAuth token payload."""

    oauth1_token: str
    oauth1_token_secret: str
    raw: dict[str, Any]

    def to_json_bytes(self) -> bytes:
        return json.dumps(self.raw, separators=(",", ":")).encode()

    @classmethod
    def from_json_bytes(cls, data: bytes) -> GarminTokens:
        raw = json.loads(data)
        return cls(
            oauth1_token=raw.get("oauth1_token", ""),
            oauth1_token_secret=raw.get("oauth1_token_secret", ""),
            raw=raw,
        )


class GarminCredentialStore:
    """Read/write encrypted Garmin tokens via Supabase REST (service role)."""

    def __init__(self, settings: Settings) -> None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
        if not settings.app_encryption_key:
            raise ValueError("APP_ENCRYPTION_KEY is required")
        self._base_url = settings.supabase_url.rstrip("/")
        self._service_key = settings.supabase_service_role_key
        self._encryption_key = settings.app_encryption_key
        self._headers = {
            "apikey": self._service_key,
            "Authorization": f"Bearer {self._service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }

    def _rest_url(self, table: str) -> str:
        return f"{self._base_url}/rest/v1/{table}"

    def store_tokens(self, user_id: str, tokens: GarminTokens) -> None:
        """Encrypt and upsert token blob for user."""
        plaintext = tokens.to_json_bytes()
        ciphertext = encrypt(plaintext, key=self._encryption_key)

        payload = {
            "user_id": user_id,
            "token_ciphertext": ciphertext.decode(),
        }

        resp = httpx.post(
            self._rest_url("garmin_credentials"),
            headers={
                **self._headers,
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        log.info("garmin_credentials.stored", user_id=user_id)

    def load_tokens(self, user_id: str) -> GarminTokens | None:
        """Load and decrypt token blob for user. Returns None if not found."""
        resp = httpx.get(
            self._rest_url("garmin_credentials"),
            params={"user_id": f"eq.{user_id}", "select": "token_ciphertext"},
            headers=self._headers,
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            return None

        ciphertext = rows[0]["token_ciphertext"].encode()
        try:
            plaintext = decrypt(ciphertext, key=self._encryption_key)
        except EncryptionError:
            log.error("garmin_credentials.decrypt_failed", user_id=user_id)
            return None

        return GarminTokens.from_json_bytes(plaintext)

    def delete_tokens(self, user_id: str) -> None:
        """Remove token blob for user."""
        resp = httpx.delete(
            self._rest_url("garmin_credentials"),
            params={"user_id": f"eq.{user_id}"},
            headers=self._headers,
            timeout=10,
        )
        resp.raise_for_status()
        log.info("garmin_credentials.deleted", user_id=user_id)
