"""Create the event store tables."""

import sqlalchemy as sa
from alembic import op

revision = "001_initial_event_store"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_records",
        sa.Column("event_id", sa.String(80), primary_key=True),
        sa.Column("aggregate_id", sa.String(80), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("causation_id", sa.String(80)),
        sa.Column("correlation_id", sa.String(80), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("aggregate_id", "aggregate_version"),
    )
    op.create_index("ix_event_records_aggregate_id", "event_records", ["aggregate_id"])
    op.create_index("ix_event_records_event_type", "event_records", ["event_type"])
    op.create_index("ix_event_records_correlation_id", "event_records", ["correlation_id"])
    op.create_index("ix_event_records_idempotency_key", "event_records", ["idempotency_key"])
    op.create_table(
        "idempotency_records",
        sa.Column("key", sa.String(160), primary_key=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("decision_id", sa.String(80), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
    )
    op.create_table(
        "player_snapshots",
        sa.Column("player_id", sa.String(80), primary_key=True),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
    )
    op.create_table(
        "outbox_records",
        sa.Column("event_id", sa.String(80), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("last_error", sa.Text()),
    )


def downgrade() -> None:
    op.drop_table("outbox_records")
    op.drop_table("player_snapshots")
    op.drop_table("idempotency_records")
    op.drop_index("ix_event_records_idempotency_key", table_name="event_records")
    op.drop_index("ix_event_records_correlation_id", table_name="event_records")
    op.drop_index("ix_event_records_event_type", table_name="event_records")
    op.drop_index("ix_event_records_aggregate_id", table_name="event_records")
    op.drop_table("event_records")
