"""Provider-connection test: verifies credentials without sending any user content."""

import asyncio

import httpx

from app.adapters.openai_compat import OpenAICompatAdapter
from app.core.config import get_settings
from app.db.models import ProviderConnection
from app.gateway.egress import probe_cloud
from app.keys.vault import EncryptedKey


def test_connection(connection: ProviderConnection) -> str:
    settings = get_settings()
    if settings.fake_providers:
        return "ok"
    encrypted = EncryptedKey(
        connection.key_ciphertext, connection.key_nonce, connection.key_version
    )

    def factory(api_key: str):
        return OpenAICompatAdapter(
            connection.base_url,
            "unused",
            api_key,
            httpx.AsyncClient(timeout=settings.provider_timeout_s),
        )

    try:
        ok = asyncio.run(probe_cloud(factory, encrypted, settings.key_vault_master_key))
    except Exception:
        return "failed"
    return "ok" if ok else "failed"


test_connection.__test__ = False  # not a pytest test
