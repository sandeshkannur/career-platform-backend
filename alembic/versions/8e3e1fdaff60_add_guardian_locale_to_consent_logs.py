"""add guardian_locale to consent_logs

Revision ID: 8e3e1fdaff60
Revises: c2e8f5a9d6b1
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "8e3e1fdaff60"
down_revision = "c2e8f5a9d6b1"
branch_labels = None
depends_on = None


def upgrade():
    # Additive only. Nullable so existing rows are untouched; new rows get
    # "en" via server_default.
    op.add_column(
        "consent_logs",
        sa.Column("guardian_locale", sa.String(length=10), nullable=True, server_default="en"),
    )


def downgrade():
    op.drop_column("consent_logs", "guardian_locale")
