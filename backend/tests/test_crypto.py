import base64

import pytest
from app.core.crypto import decrypt_secret, encrypt_secret
from app.keys.vault import rotate_provider_key, seal_provider_key

KEY = base64.b64encode(b"0" * 32).decode()
NEW_KEY = base64.b64encode(b"1" * 32).decode()


def test_aes_gcm_uses_unique_nonce_and_round_trips() -> None:
    first = encrypt_secret("provider-secret", KEY)
    second = encrypt_secret("provider-secret", KEY)

    assert first[1] != second[1]
    assert decrypt_secret(*first, KEY) == "provider-secret"


def test_tampering_and_wrong_key_fail_closed() -> None:
    ciphertext, nonce = encrypt_secret("provider-secret", KEY)
    with pytest.raises(ValueError):
        decrypt_secret(ciphertext[:-1] + b"x", nonce, KEY)
    with pytest.raises(ValueError):
        decrypt_secret(ciphertext, nonce, NEW_KEY)


def test_key_rotation_preserves_secret_and_changes_version() -> None:
    original = seal_provider_key("provider-secret", KEY, key_version=1)
    rotated = rotate_provider_key(original, KEY, NEW_KEY, new_key_version=2)

    assert rotated.key_version == 2
    assert rotated.ciphertext != original.ciphertext
    assert decrypt_secret(rotated.ciphertext, rotated.nonce, NEW_KEY) == "provider-secret"
