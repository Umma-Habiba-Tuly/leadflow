"""Reversible encryption for secrets we must be able to use later (SMTP passwords).

Passwords for logging INTO our app are hashed (one-way). These are different: we need the
original to log in to the client's mail server, so they are encrypted with a key that lives
only in the environment, never in the database.
"""
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class CryptoError(RuntimeError):
    pass


class CryptoNotConfigured(CryptoError):
    pass


def _fernet() -> Fernet:
    if not settings.encryption_key:
        raise CryptoNotConfigured("ENCRYPTION_KEY is not set")
    try:
        return Fernet(settings.encryption_key.encode())
    except (ValueError, TypeError):
        raise CryptoNotConfigured("ENCRYPTION_KEY is not a valid Fernet key")


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        # Wrong key, or the stored value was altered.
        raise CryptoError("Stored secret could not be decrypted (wrong ENCRYPTION_KEY?)")
