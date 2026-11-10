from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(16), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    connections: Mapped[list["ProviderConnection"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(512))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rotated_from: Mapped[str | None] = mapped_column(String(36), nullable=True)
    user: Mapped[User] = relationship(back_populates="refresh_tokens")


class ProviderConnection(Base):
    __tablename__ = "provider_connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    base_url: Mapped[str] = mapped_column(String(512))
    label: Mapped[str] = mapped_column(String(100))
    key_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    key_nonce: Mapped[bytes] = mapped_column(LargeBinary)
    key_version: Mapped[int] = mapped_column(Integer, default=1)
    last4: Mapped[str] = mapped_column(String(4))
    status: Mapped[str] = mapped_column(String(32), default="untested")
    monthly_budget_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    user: Mapped[User] = relationship(back_populates="connections")


class Model(Base):
    __tablename__ = "models"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(64))
    endpoint: Mapped[str] = mapped_column(String(512))
    context_limit: Mapped[int] = mapped_column(Integer)
    max_output: Mapped[int] = mapped_column(Integer)
    provider_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tokenizer: Mapped[str] = mapped_column(String(64), default="fallback")
    quant: Mapped[str | None] = mapped_column(String(64), nullable=True)
    min_ram_gb: Mapped[float] = mapped_column(Float, default=0)
    min_vram_gb: Mapped[float] = mapped_column(Float, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class ModelPrice(Base):
    __tablename__ = "model_prices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    model_id: Mapped[str] = mapped_column(ForeignKey("models.id"), index=True)
    input_per_mtok: Mapped[float] = mapped_column(Float)
    output_per_mtok: Mapped[float] = mapped_column(Float)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    source: Mapped[str] = mapped_column(String(200))


class ModelHealth(Base):
    __tablename__ = "model_health"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    model_id: Mapped[str] = mapped_column(ForeignKey("models.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    ok: Mapped[bool] = mapped_column(Boolean)
    p50_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    err_rate: Mapped[float] = mapped_column(Float, default=0)


class UserModelPref(Base):
    __tablename__ = "user_model_prefs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    model_id: Mapped[str] = mapped_column(ForeignKey("models.id"), index=True)
    connection_id: Mapped[str | None] = mapped_column(
        ForeignKey("provider_connections.id"), nullable=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    tier: Mapped[str] = mapped_column(String(16))


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    mode: Mapped[str] = mapped_column(String(16), default="local_only")
    label: Mapped[str] = mapped_column(String(16), default="public")
    persist_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    label: Mapped[str] = mapped_column(String(16), default="public")
    pages: Mapped[int] = mapped_column(Integer)
    bytes: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    page: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    tokens: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(16), default="public")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(String(16), default="public")
    tokens: Mapped[int] = mapped_column(Integer)
    event_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ConsentRecord(Base):
    __tablename__ = "consents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    destination_model_id: Mapped[str] = mapped_column(String(200))
    payload_hash: Mapped[str] = mapped_column(String(64))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InstitutionalPolicyRecord(Base):
    __tablename__ = "institutional_policy"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    allow_cloud: Mapped[bool] = mapped_column(Boolean, default=True)
    forbid_labels: Mapped[str] = mapped_column(String(255), default="")
    updated_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PolicyVersionRecord(Base):
    __tablename__ = "policy_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(64), unique=True)
    config_hash: Mapped[str] = mapped_column(String(64))
    deployment: Mapped[str] = mapped_column(String(64), default="default")
    kind: Mapped[str] = mapped_column(String(16), default="rules")
    params_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    epsilon: Mapped[float | None] = mapped_column(Float, nullable=True)
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RoutingEvent(Base):
    __tablename__ = "routing_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    policy_name: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[str] = mapped_column(String(64))
    selected_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    rule_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    estimated_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    measured_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    measured_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    routing_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    generation_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    explanation: Mapped[str] = mapped_column(String(500))
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    task_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    features_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    eligible_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    removed_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    shadow_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_prob: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    measured_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ttft_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    abstained: Mapped[bool] = mapped_column(Boolean, default=False)
    abstain_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    consent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    effective_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RoutingAttempt(Base):
    __tablename__ = "routing_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    event_id: Mapped[str] = mapped_column(ForeignKey("routing_events.id"), index=True)
    model: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32))
    error_class: Mapped[str | None] = mapped_column(String(100), nullable=True)
    measured_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    ttft_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PrivacyFinding(Base):
    """Coarse detector output only: entity type and count, never matched text."""

    __tablename__ = "privacy_findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    event_id: Mapped[str] = mapped_column(ForeignKey("routing_events.id"), index=True)
    scope: Mapped[str] = mapped_column(String(16))
    entity_type: Mapped[str] = mapped_column(String(32))
    count: Mapped[int] = mapped_column(Integer)
    detector_version: Mapped[str] = mapped_column(String(32))


class BudgetLedger(Base):
    __tablename__ = "budget_ledger"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    connection_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="settle")
    usd: Mapped[float] = mapped_column(Float)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RatingItem(Base):
    """A response shown to raters. ``model`` is server-side only and never serialised."""

    __tablename__ = "rating_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    task_type: Mapped[str] = mapped_column(String(32), default="qa")
    prompt: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text, default="")
    response: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RatingAssignment(Base):
    __tablename__ = "rating_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    item_id: Mapped[str] = mapped_column(ForeignKey("rating_items.id"), index=True)
    rater_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    event_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    item_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    rater_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source: Mapped[str] = mapped_column(String(8))
    correctness: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relevance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completeness: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usefulness: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auto_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    blind: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ScoredOutcome(Base):
    __tablename__ = "scored_outcomes"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    model: Mapped[str] = mapped_column(String(200), index=True)
    quality: Mapped[float | None] = mapped_column(Float, nullable=True)
    q_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reward: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    features_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    usable_for_update: Mapped[bool] = mapped_column(Boolean, default=False)
    consumed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(100))
    git_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config_hash: Mapped[str] = mapped_column(String(64))
    seed: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
