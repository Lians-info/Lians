"""Add stripe_customer_id to namespace_policies for usage metering

Revision ID: 0007_billing
Revises: 0006_audit_hash_chain
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_billing"
down_revision = "0006_audit_hash_chain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "namespace_policies",
        sa.Column("stripe_customer_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("namespace_policies", "stripe_customer_id")
