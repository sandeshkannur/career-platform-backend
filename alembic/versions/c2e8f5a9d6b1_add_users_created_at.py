"""add users.created_at

Two-step add so PRE-EXISTING rows stay NULL (their real creation date was
never captured — backfilling now() would fabricate data) while all FUTURE
rows are stamped by the DB default:
  1. ADD COLUMN with no default  -> existing rows get NULL
  2. SET DEFAULT now()           -> new inserts get stamped

Revision ID: c2e8f5a9d6b1
Revises: d8f3b6a1c4e7
Create Date: 2026-07-09

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c2e8f5a9d6b1"
down_revision = "d8f3b6a1c4e7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("users", "created_at", server_default=sa.func.now())


def downgrade():
    op.drop_column("users", "created_at")
