"""Add users.is_active for soft-delete/deactivation

Additive, backward-compatible: defaults to true for all existing rows.
Introduced for admin counsellor-account management (soft delete = deactivate;
rows are never hard-deleted, matching platform convention).

Revision ID: c8e2f4a6b9d3
Revises: b7c9d2e4f6a1
Create Date: 2026-07-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8e2f4a6b9d3'
down_revision: Union[str, None] = 'b7c9d2e4f6a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("users", "is_active")
