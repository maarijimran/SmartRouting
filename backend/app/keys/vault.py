from dataclasses import dataclass

from app.core.crypto import decrypt_secret, encrypt_secret


@dataclass(frozen=True)
class EncryptedKey:
    ciphertext: bytes
    nonce: bytes
    key_version: int = 1


def seal_provider_key(api_key: str, master_key: str, key_version: int = 1) -> EncryptedKey:
    ciphertext, nonce = encrypt_secret(api_key, master_key)
    return EncryptedKey(ciphertext, nonce, key_version)


def open_provider_key(encrypted: EncryptedKey, master_key: str) -> str:
    return decrypt_secret(encrypted.ciphertext, encrypted.nonce, master_key)


def rotate_provider_key(
    encrypted: EncryptedKey,
    old_master_key: str,
    new_master_key: str,
    new_key_version: int,
) -> EncryptedKey:
    plaintext = open_provider_key(encrypted, old_master_key)
    return seal_provider_key(plaintext, new_master_key, new_key_version)
