"""demo mode: documents.scope and runs.actor

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-18
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing rows get the defaults: documents stay private, runs belong to the admin.
    op.add_column(
        "documents",
        sa.Column("scope", sa.String(16), nullable=False, server_default="private"),
    )
    op.add_column(
        "runs",
        sa.Column("actor", sa.String(16), nullable=False, server_default="admin"),
    )


def downgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.drop_column("actor")
    with op.batch_alter_table("documents") as batch:
        batch.drop_column("scope")
