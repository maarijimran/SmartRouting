"""Create Phase 1 identity and provider tables."""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(512), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("rotated_from", sa.String(36)),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_table(
        "provider_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("base_url", sa.String(512), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("key_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("key_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last4", sa.String(4), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="untested"),
        sa.Column("monthly_budget_usd", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_provider_connections_user_id", "provider_connections", ["user_id"])
    op.create_table(
        "models",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(200), nullable=False, unique=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("endpoint", sa.String(512), nullable=False),
        sa.Column("context_limit", sa.Integer(), nullable=False),
        sa.Column("max_output", sa.Integer(), nullable=False),
        sa.Column("tokenizer", sa.String(64), nullable=False, server_default="fallback"),
        sa.Column("quant", sa.String(64)),
        sa.Column("min_ram_gb", sa.Float(), nullable=False, server_default="0"),
        sa.Column("min_vram_gb", sa.Float(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_models_slug", "models", ["slug"])
    op.create_table(
        "model_prices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("model_id", sa.String(36), sa.ForeignKey("models.id"), nullable=False),
        sa.Column("input_per_mtok", sa.Float(), nullable=False),
        sa.Column("output_per_mtok", sa.Float(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(200), nullable=False),
    )
    op.create_index("ix_model_prices_model_id", "model_prices", ["model_id"])
    op.create_table(
        "model_health",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("model_id", sa.String(36), sa.ForeignKey("models.id"), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("p50_ms", sa.Float()),
        sa.Column("err_rate", sa.Float(), nullable=False, server_default="0"),
    )
    op.create_index("ix_model_health_model_id", "model_health", ["model_id"])
    op.create_table(
        "user_model_prefs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("model_id", sa.String(36), sa.ForeignKey("models.id"), nullable=False),
        sa.Column("connection_id", sa.String(36), sa.ForeignKey("provider_connections.id")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("tier", sa.String(16), nullable=False),
    )
    op.create_index("ix_user_model_prefs_user_id", "user_model_prefs", ["user_id"])
    op.create_index("ix_user_model_prefs_model_id", "user_model_prefs", ["model_id"])
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False, server_default="local_only"),
        sa.Column("label", sa.String(16), nullable=False, server_default="public"),
        sa.Column("persist_opt_in", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])
    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("chat_sessions.id"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("label", sa.String(16), nullable=False, server_default="public"),
        sa.Column("pages", sa.Integer(), nullable=False),
        sa.Column("bytes", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_documents_session_id", "documents", ["session_id"])
    op.create_table(
        "chunks",
        sa.Column("id", sa.String(24), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(16), nullable=False, server_default="public"),
    )
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("chat_sessions.id"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("label", sa.String(16), nullable=False, server_default="public"),
        sa.Column("tokens", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"])
    op.create_table(
        "consents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("chat_sessions.id"), nullable=False),
        sa.Column("destination_model_id", sa.String(36), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_consents_user_id", "consents", ["user_id"])
    op.create_index("ix_consents_session_id", "consents", ["session_id"])
    op.create_table(
        "institutional_policy",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("allow_cloud", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("forbid_labels", sa.String(255), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "policy_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("version", sa.String(64), nullable=False, unique=True),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("deployment", sa.String(64), nullable=False, server_default="default"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "routing_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("chat_sessions.id"), nullable=False),
        sa.Column("policy_name", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("selected_model", sa.String(200)),
        sa.Column("rule_id", sa.String(100)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("estimated_input_tokens", sa.Integer()),
        sa.Column("measured_input_tokens", sa.Integer()),
        sa.Column("estimated_cost_usd", sa.Float()),
        sa.Column("measured_cost_usd", sa.Float()),
        sa.Column("routing_latency_ms", sa.Float()),
        sa.Column("generation_latency_ms", sa.Float()),
        sa.Column("explanation", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_routing_events_session_id", "routing_events", ["session_id"])
    op.create_table(
        "routing_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_id", sa.String(36), sa.ForeignKey("routing_events.id"), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_class", sa.String(100)),
        sa.Column("measured_cost_usd", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_routing_attempts_event_id", "routing_attempts", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_messages_session_id", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_consents_session_id", table_name="consents")
    op.drop_index("ix_consents_user_id", table_name="consents")
    op.drop_table("consents")
    op.drop_table("institutional_policy")
    op.drop_index("ix_routing_attempts_event_id", table_name="routing_attempts")
    op.drop_table("routing_attempts")
    op.drop_index("ix_routing_events_session_id", table_name="routing_events")
    op.drop_table("routing_events")
    op.drop_table("policy_versions")
    op.drop_index("ix_chunks_document_id", table_name="chunks")
    op.drop_table("chunks")
    op.drop_index("ix_documents_session_id", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_chat_sessions_user_id", table_name="chat_sessions")
    op.drop_table("chat_sessions")
    op.drop_index("ix_user_model_prefs_model_id", table_name="user_model_prefs")
    op.drop_index("ix_user_model_prefs_user_id", table_name="user_model_prefs")
    op.drop_table("user_model_prefs")
    op.drop_index("ix_model_health_model_id", table_name="model_health")
    op.drop_table("model_health")
    op.drop_index("ix_model_prices_model_id", table_name="model_prices")
    op.drop_table("model_prices")
    op.drop_index("ix_models_slug", table_name="models")
    op.drop_table("models")
    op.drop_index("ix_provider_connections_user_id", table_name="provider_connections")
    op.drop_table("provider_connections")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
