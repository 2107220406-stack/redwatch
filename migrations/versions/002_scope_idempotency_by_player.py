"""Scope idempotency records by player identity."""

import sqlalchemy as sa
from alembic import op

revision = "002_scope_idempotency_by_player"
down_revision = "001_initial_event_store"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "idempotency_records_new",
        sa.Column("player_id", sa.String(80), nullable=False),
        sa.Column("key", sa.String(160), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("decision_id", sa.String(80), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("player_id", "key"),
    )
    op.execute(
        sa.text(
            "INSERT INTO idempotency_records_new "
            "(player_id, key, request_hash, decision_id, response) "
            "SELECT 'legacy', key, request_hash, decision_id, response "
            "FROM idempotency_records"
        )
    )
    op.drop_table("idempotency_records")
    op.rename_table("idempotency_records_new", "idempotency_records")


def downgrade() -> None:
    op.create_table(
        "idempotency_records_old",
        sa.Column("key", sa.String(160), primary_key=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("decision_id", sa.String(80), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
    )
    op.execute(
        sa.text(
            "INSERT INTO idempotency_records_old "
            "(key, request_hash, decision_id, response) "
            "SELECT key, request_hash, decision_id, response "
            "FROM idempotency_records"
        )
    )
    op.drop_table("idempotency_records")
    op.rename_table("idempotency_records_old", "idempotency_records")
