"""Builds adapters for registry models. The only place concrete adapters are chosen."""

import httpx

from app.adapters.base import Adapter
from app.adapters.fake import FakeAdapter, FakeScript
from app.adapters.ollama import OllamaAdapter
from app.adapters.openai_compat import OpenAICompatAdapter
from app.core.config import Settings
from app.db.models import Model, ProviderConnection
from app.gateway.egress import SealedCloudAdapter
from app.keys.vault import EncryptedKey


def _client(settings: Settings) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=settings.provider_timeout_s)


def provider_model_id(model: Model) -> str:
    return model.provider_model or model.slug


def build_local_adapter(model: Model, settings: Settings) -> Adapter:
    if settings.fake_providers:
        return FakeAdapter(FakeScript(text=f"[{model.slug}] fake local answer"))
    return OllamaAdapter(settings.ollama_url, provider_model_id(model), _client(settings))


class FakeCloudAdapter(FakeAdapter):
    """Fake adapter flagged as cloud so the egress re-scan path is exercised."""

    kind = "cloud"


def build_cloud_adapter(
    model: Model, connection: ProviderConnection, settings: Settings
) -> Adapter:
    if settings.fake_providers:
        cost = 0.0001 if "cheap" in model.slug else 0.001
        return FakeCloudAdapter(FakeScript(text=f"[{model.slug}] fake cloud answer", cost_usd=cost))
    encrypted = EncryptedKey(
        connection.key_ciphertext, connection.key_nonce, connection.key_version
    )

    def factory(api_key: str) -> Adapter:
        return OpenAICompatAdapter(
            connection.base_url, provider_model_id(model), api_key, _client(settings)
        )

    return SealedCloudAdapter(encrypted, settings.key_vault_master_key, factory)


class BlockedAdapter:
    """Placeholder for a cloud candidate the privacy gate already rejected.

    No real adapter is constructed (and no key material touched) for blocked models.
    """

    kind = "cloud"

    async def generate(self, messages, params):
        from app.gateway.egress import EgressBlocked

        raise EgressBlocked("Candidate was blocked before dispatch")
        yield  # pragma: no cover - makes this an async generator

    async def health(self) -> bool:
        return False

    def count_tokens(self, messages) -> int:
        return 0
