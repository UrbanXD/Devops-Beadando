"""Create user conversion history.

Revision ID: 0003_create_conversion_history
Revises: 0002_create_refresh_sessions
Create Date: 2026-11-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_create_conversion_history"
down_revision: Union[str, None] = "0002_create_refresh_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversion_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("output_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=64), nullable=False),
        sa.Column("output_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        "ix_conversion_history_user_created_at",
        "conversion_history",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversion_history_user_created_at",
        table_name="conversion_history",
    )
    op.drop_table("conversion_history")
