"""add password_reset_logs table

Revision ID: 4ccef63917c9
Revises: 8e3e1fdaff60
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

revision = "4ccef63917c9"
down_revision = "8e3e1fdaff60"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "password_reset_logs",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("method", sa.String(length=32), nullable=False, index=True),
        sa.Column("status", sa.String(length=32), nullable=False, index=True),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("initiated_by_admin_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("token_jti", sa.String(length=128), nullable=True, index=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_table("password_reset_logs")
