"""Symmetric encryption for Garmin OAuth token blobs.

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography` library.
The key is loaded from APP_ENCRYPTION_KEY in environment / .env.

Key format: 32-byte URL-safe base64 string (Fernet.generate_key() produces this).
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class EncryptionError(Exception):
    """Raised when encryption or decryption fails."""


def encrypt(plaintext: bytes, *, key: str) -> bytes:
    """Encrypt plaintext bytes and return ciphertext bytes."""
    try:
        f = Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise EncryptionError("Invalid encryption key format") from exc
    return f.encrypt(plaintext)


def decrypt(ciphertext: bytes, *, key: str) -> bytes:
    """Decrypt ciphertext bytes and return plaintext bytes."""
    try:
        f = Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise EncryptionError("Invalid encryption key format") from exc
    try:
        return f.decrypt(ciphertext)
    except InvalidToken as exc:
        raise EncryptionError("Decryption failed — wrong key or corrupted data") from exc


def generate_key() -> str:
    """Generate a new Fernet key (URL-safe base64, 32 bytes)."""
    return Fernet.generate_key().decode()
