"""Persist dispatch intent and grant a bounded retry cycle on redrive."""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "deliveries", sa.Column("cycle_attempt_count", sa.Integer(), nullable=False, server_default="0")
    )
    op.execute("UPDATE deliveries SET cycle_attempt_count = attempt_count")
    op.create_table(
        "dispatch_starts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("delivery_id", sa.String(36), sa.ForeignKey("deliveries.id"), nullable=False),
        sa.Column("lease_version", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(100), nullable=False),
        sa.Column("region", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trace_id", sa.String(32), nullable=False),
        sa.UniqueConstraint("delivery_id", "lease_version"),
    )
    op.create_index("ix_dispatch_starts_delivery_id", "dispatch_starts", ["delivery_id"])


def downgrade():
    op.drop_table("dispatch_starts")
    op.drop_column("deliveries", "cycle_attempt_count")
