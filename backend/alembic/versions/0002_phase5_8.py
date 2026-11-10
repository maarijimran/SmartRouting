"""phase5-8 tables and routing columns

Revision ID: 0002_phase5_8
Revises: 0001_initial
Create Date: 2026-11-10 22:02:38.388546
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_phase5_8"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "budget_ledger",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("event_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("usd", sa.Float(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_budget_ledger_connection_id"), "budget_ledger", ["connection_id"], unique=False
    )
    op.create_index(op.f("ix_budget_ledger_user_id"), "budget_ledger", ["user_id"], unique=False)
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("git_sha", sa.String(length=64), nullable=True),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "feedback",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=True),
        sa.Column("item_id", sa.String(length=36), nullable=True),
        sa.Column("rater_id", sa.String(length=36), nullable=True),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("correctness", sa.Integer(), nullable=True),
        sa.Column("relevance", sa.Integer(), nullable=True),
        sa.Column("completeness", sa.Integer(), nullable=True),
        sa.Column("usefulness", sa.Integer(), nullable=True),
        sa.Column("auto_score", sa.Float(), nullable=True),
        sa.Column("blind", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_feedback_event_id"), "feedback", ["event_id"], unique=False)
    op.create_index(op.f("ix_feedback_item_id"), "feedback", ["item_id"], unique=False)
    op.create_table(
        "rating_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=True),
        sa.Column("task_type", sa.String(length=32), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "scored_outcomes",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("quality", sa.Float(), nullable=True),
        sa.Column("q_source", sa.String(length=16), nullable=True),
        sa.Column("reward", sa.Float(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("features_json", sa.Text(), nullable=True),
        sa.Column("usable_for_update", sa.Boolean(), nullable=False),
        sa.Column("consumed_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(op.f("ix_scored_outcomes_model"), "scored_outcomes", ["model"], unique=False)
    op.create_table(
        "rating_assignments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("rater_id", sa.String(length=36), nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["rating_items.id"],
        ),
        sa.ForeignKeyConstraint(
            ["rater_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_rating_assignments_item_id"), "rating_assignments", ["item_id"], unique=False
    )
    op.create_index(
        op.f("ix_rating_assignments_rater_id"), "rating_assignments", ["rater_id"], unique=False
    )
    op.create_table(
        "privacy_findings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("detector_version", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["routing_events.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_privacy_findings_event_id"), "privacy_findings", ["event_id"], unique=False
    )
    with op.batch_alter_table("consents") as batch:
        batch.alter_column(
            "destination_model_id",
            existing_type=sa.String(length=36),
            type_=sa.String(length=200),
            existing_nullable=False,
        )
    op.add_column("chunks", sa.Column("page", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("messages", sa.Column("event_id", sa.String(length=36), nullable=True))
    op.create_index(op.f("ix_messages_event_id"), "messages", ["event_id"], unique=False)
    op.add_column("models", sa.Column("provider_model", sa.String(length=200), nullable=True))
    op.drop_index(op.f("ix_models_slug"), table_name="models")
    op.create_index(op.f("ix_models_slug"), "models", ["slug"], unique=True)
    op.add_column(
        "policy_versions",
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="rules"),
    )
    op.add_column("policy_versions", sa.Column("params_json", sa.Text(), nullable=True))
    op.add_column("policy_versions", sa.Column("epsilon", sa.Float(), nullable=True))
    op.add_column("policy_versions", sa.Column("parent_id", sa.String(length=36), nullable=True))
    op.add_column(
        "routing_attempts",
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column("routing_attempts", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("routing_attempts", sa.Column("output_tokens", sa.Integer(), nullable=True))
    op.add_column("routing_attempts", sa.Column("latency_ms", sa.Float(), nullable=True))
    op.add_column("routing_attempts", sa.Column("ttft_ms", sa.Float(), nullable=True))
    op.add_column("routing_events", sa.Column("user_id", sa.String(length=36), nullable=True))
    op.add_column("routing_events", sa.Column("task_type", sa.String(length=32), nullable=True))
    op.add_column("routing_events", sa.Column("features_json", sa.Text(), nullable=True))
    op.add_column("routing_events", sa.Column("eligible_json", sa.Text(), nullable=True))
    op.add_column("routing_events", sa.Column("removed_json", sa.Text(), nullable=True))
    op.add_column("routing_events", sa.Column("shadow_json", sa.Text(), nullable=True))
    op.add_column("routing_events", sa.Column("action_prob", sa.Float(), nullable=True))
    op.add_column(
        "routing_events", sa.Column("estimated_output_tokens", sa.Integer(), nullable=True)
    )
    op.add_column("routing_events", sa.Column("estimated_latency_ms", sa.Float(), nullable=True))
    op.add_column(
        "routing_events", sa.Column("measured_output_tokens", sa.Integer(), nullable=True)
    )
    op.add_column("routing_events", sa.Column("ttft_ms", sa.Float(), nullable=True))
    op.add_column(
        "routing_events",
        sa.Column("abstained", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "routing_events", sa.Column("abstain_reason", sa.String(length=500), nullable=True)
    )
    op.add_column("routing_events", sa.Column("consent_id", sa.String(length=36), nullable=True))
    op.add_column(
        "routing_events", sa.Column("effective_label", sa.String(length=16), nullable=True)
    )
    op.create_index(op.f("ix_routing_events_user_id"), "routing_events", ["user_id"], unique=False)
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)
    op.drop_index(op.f("ix_routing_events_user_id"), table_name="routing_events")
    op.drop_column("routing_events", "effective_label")
    op.drop_column("routing_events", "consent_id")
    op.drop_column("routing_events", "abstain_reason")
    op.drop_column("routing_events", "abstained")
    op.drop_column("routing_events", "ttft_ms")
    op.drop_column("routing_events", "measured_output_tokens")
    op.drop_column("routing_events", "estimated_latency_ms")
    op.drop_column("routing_events", "estimated_output_tokens")
    op.drop_column("routing_events", "action_prob")
    op.drop_column("routing_events", "shadow_json")
    op.drop_column("routing_events", "removed_json")
    op.drop_column("routing_events", "eligible_json")
    op.drop_column("routing_events", "features_json")
    op.drop_column("routing_events", "task_type")
    op.drop_column("routing_events", "user_id")
    op.drop_column("routing_attempts", "ttft_ms")
    op.drop_column("routing_attempts", "latency_ms")
    op.drop_column("routing_attempts", "output_tokens")
    op.drop_column("routing_attempts", "input_tokens")
    op.drop_column("routing_attempts", "attempt_no")
    op.drop_column("policy_versions", "parent_id")
    op.drop_column("policy_versions", "epsilon")
    op.drop_column("policy_versions", "params_json")
    op.drop_column("policy_versions", "kind")
    op.drop_index(op.f("ix_models_slug"), table_name="models")
    op.create_index(op.f("ix_models_slug"), "models", ["slug"], unique=False)
    op.drop_column("models", "provider_model")
    op.drop_column("chunks", "page")
    op.drop_index(op.f("ix_messages_event_id"), table_name="messages")
    op.drop_column("messages", "event_id")
    with op.batch_alter_table("consents") as batch:
        batch.alter_column(
            "destination_model_id",
            existing_type=sa.String(length=200),
            type_=sa.String(length=36),
            existing_nullable=False,
        )
    op.drop_index(op.f("ix_privacy_findings_event_id"), table_name="privacy_findings")
    op.drop_table("privacy_findings")
    op.drop_index(op.f("ix_rating_assignments_rater_id"), table_name="rating_assignments")
    op.drop_index(op.f("ix_rating_assignments_item_id"), table_name="rating_assignments")
    op.drop_table("rating_assignments")
    op.drop_index(op.f("ix_scored_outcomes_model"), table_name="scored_outcomes")
    op.drop_table("scored_outcomes")
    op.drop_table("rating_items")
    op.drop_index(op.f("ix_feedback_item_id"), table_name="feedback")
    op.drop_index(op.f("ix_feedback_event_id"), table_name="feedback")
    op.drop_table("feedback")
    op.drop_table("eval_runs")
    op.drop_index(op.f("ix_budget_ledger_user_id"), table_name="budget_ledger")
    op.drop_index(op.f("ix_budget_ledger_connection_id"), table_name="budget_ledger")
    op.drop_table("budget_ledger")
