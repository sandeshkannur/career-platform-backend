"""add phone_number to users, create login_otps table

Revision ID: f6a1b2c3d4e5
Revises: a9b0c1d2e3f4
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = "f6a1b2c3d4e5"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade():
    # Stage 1: additive only. email stays required; phone is a second,
    # optional door into the same account.
    op.add_column(
        "users",
        sa.Column("phone_number", sa.String(length=20), nullable=True),
    )
    op.create_index(
        "ix_users_phone_number", "users", ["phone_number"], unique=True
    )

    op.create_table(
        "login_otps",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("phone_number", sa.String(length=20), nullable=False, index=True),
        sa.Column("otp_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_login_otps_phone_created", "login_otps", ["phone_number", "created_at"]
    )


def downgrade():
    op.drop_index("ix_login_otps_phone_created", table_name="login_otps")
    op.drop_table("login_otps")
    op.drop_index("ix_users_phone_number", table_name="users")
    op.drop_column("users", "phone_number")