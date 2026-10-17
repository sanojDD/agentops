"""initial schema: documents, chunks, runs

Revision ID: 0001
Revises:
Create Date: 2026-10-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("pages", sa.Integer, nullable=False),
        sa.Column("chunk_count", sa.Integer, nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "doc_id",
            sa.String(32),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("page", sa.Integer, nullable=True),
        sa.Column("text", sa.Text, nullable=False),
    )
    op.create_index("ix_chunks_doc_id", "chunks", ["doc_id"])
    op.create_table(
        "runs",
        sa.Column("run_id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("answer", sa.Text, nullable=False),
        sa.Column("fallback", sa.Boolean, nullable=False),
        sa.Column("fallback_reason", sa.String(32), nullable=True),
        sa.Column("error_kind", sa.String(32), nullable=True),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("support_score", sa.Float, nullable=True),
        sa.Column("retrieval_attempts", sa.Integer, nullable=False),
        sa.Column("generate_attempts", sa.Integer, nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("steps", sa.JSON, nullable=False),
        sa.Column("sources", sa.JSON, nullable=False),
    )
    op.create_index("ix_runs_created_at", "runs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_runs_created_at", table_name="runs")
    op.drop_table("runs")
    op.drop_index("ix_chunks_doc_id", table_name="chunks")
    op.drop_table("chunks")
    op.drop_table("documents")
