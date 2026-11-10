import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _decode_master_key(master_key: str) -> bytes:
    try:
        decoded = base64.b64decode(master_key, validate=True)
    except Exception as exc:
        raise ValueError("KEY_VAULT_MASTER_KEY must be base64 encoded") from exc
    if len(decoded) != 32:
        raise ValueError("KEY_VAULT_MASTER_KEY must decode to 32 bytes")
    return decoded


def encrypt_secret(
    secret: str, master_key: str, associated_data: bytes = b""
) -> tuple[bytes, bytes]:
    key = _decode_master_key(master_key)
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, secret.encode("utf-8"), associated_data)
    return ciphertext, nonce


def decrypt_secret(
    ciphertext: bytes,
    nonce: bytes,
    master_key: str,
    associated_data: bytes = b"",
) -> str:
    key = _decode_master_key(master_key)
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, associated_data)
    except InvalidTag as exc:
        raise ValueError("Unable to decrypt secret") from exc
    return plaintext.decode("utf-8")
