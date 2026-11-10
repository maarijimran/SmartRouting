"""The single egress point.

Everything that leaves the trust boundary is dispatched from this module:
the outbound payload is re-scanned here, and provider keys are decrypted only
here (inside ``SealedCloudAdapter``/``send_cloud``), immediately before use.
"""

from collections.abc import AsyncIterator, Callable, Sequence

from app.adapters.base import Adapter, Chunk, GenerationParams
from app.keys.vault import EncryptedKey, open_provider_key
from app.privacy.gate import GateResult, serialize_payload


class EgressBlocked(Exception):
    """Outbound payload was rejected by the privacy gate."""

    def __init__(self, message: str, reason: str = "privacy_blocked") -> None:
        super().__init__(message)
        self.reason = reason


OutboundCheck = Callable[[bytes], GateResult]


class SealedCloudAdapter:
    """Cloud adapter that holds only ciphertext until the moment of dispatch."""

    kind = "cloud"

    def __init__(
        self,
        encrypted_key: EncryptedKey,
        master_key: str,
        adapter_factory: Callable[[str], Adapter],
    ) -> None:
        self._encrypted = encrypted_key
        self._master_key = master_key
        self._factory = adapter_factory

    async def generate(
        self, messages: Sequence[dict[str, str]], params: GenerationParams
    ) -> AsyncIterator[Chunk]:
        api_key = open_provider_key(self._encrypted, self._master_key)
        adapter = self._factory(api_key)
        async for chunk in adapter.generate(messages, params):
            yield chunk

    async def health(self) -> bool:
        adapter = self._factory(open_provider_key(self._encrypted, self._master_key))
        return await adapter.health()

    def count_tokens(self, messages: Sequence[dict[str, str]]) -> int:
        return sum(len(message.get("content", "").split()) for message in messages)


async def send(
    adapter: Adapter,
    messages: Sequence[dict[str, str]],
    params: GenerationParams,
    *,
    privacy_gate: bool,
    outbound_check: OutboundCheck | None = None,
) -> AsyncIterator[Chunk]:
    """Dispatch to an adapter after the outbound gate has passed.

    Cloud adapters (``kind == "cloud"``) must supply ``outbound_check``; the final
    serialized payload is re-scanned here regardless of any earlier decision.
    """
    if not privacy_gate:
        raise EgressBlocked("Outbound privacy gate blocked the request")
    is_cloud = getattr(adapter, "kind", "local") == "cloud"
    if is_cloud and outbound_check is None:
        raise EgressBlocked("Cloud dispatch requires an outbound re-scan", "no_outbound_check")
    if outbound_check is not None:
        result = outbound_check(serialize_payload(messages))
        if not result.allowed:
            raise EgressBlocked("Outbound privacy gate blocked the request", result.reason)
    async for chunk in adapter.generate(messages, params):
        yield chunk


async def send_cloud(
    adapter_factory,
    encrypted_key: EncryptedKey,
    master_key: str,
    messages: Sequence[dict[str, str]],
    params: GenerationParams,
    *,
    privacy_gate: bool,
    gate_result: GateResult | None = None,
) -> AsyncIterator[Chunk]:
    """Decrypt immediately before constructing the cloud adapter and dispatching."""
    if not privacy_gate or gate_result is None or not gate_result.allowed:
        raise EgressBlocked("Outbound privacy gate blocked the request")
    api_key = open_provider_key(encrypted_key, master_key)
    adapter = adapter_factory(api_key)
    async for chunk in adapter.generate(messages, params):
        yield chunk


async def probe_cloud(
    adapter_factory: Callable[[str], Adapter], encrypted_key: EncryptedKey, master_key: str
) -> bool:
    """Credential/connectivity probe; sends no user content."""
    adapter = adapter_factory(open_provider_key(encrypted_key, master_key))
    return await adapter.health()
