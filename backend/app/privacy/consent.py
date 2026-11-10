from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class Consent:
    user_id: str
    session_id: str
    destination_model_id: str
    payload_hash: str
    expires_at: datetime
    revoked_at: datetime | None = None

    def valid_for(
        self,
        *,
        user_id: str,
        session_id: str,
        model_id: str,
        payload_hash: str,
        now: datetime | None = None,
    ) -> bool:
        current = now or datetime.now(UTC)
        expiry = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=UTC)
        return (
            self.revoked_at is None
            and expiry > current
            and self.user_id == user_id
            and self.session_id == session_id
            and self.destination_model_id == model_id
            and self.payload_hash == payload_hash
        )
