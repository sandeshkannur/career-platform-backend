"""add consent_logs table

Revision ID: 5c50f1279676
Revises: 3293623a055c
Create Date: 2026-03-08 10:25:36.834978

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c50f1279676'
down_revision: Union[str, None] = '3293623a055c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "consent_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("student_user_id", sa.Integer(), nullable=False),
        sa.Column("guardian_email", sa.String(length=320), nullable=False),
        sa.Column("token_jti", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(op.f("ix_consent_logs_id"), "consent_logs", ["id"], unique=False)
    op.create_index(op.f("ix_consent_logs_student_id"), "consent_logs", ["student_id"], unique=False)
    op.create_index(op.f("ix_consent_logs_student_user_id"), "consent_logs", ["student_user_id"], unique=False)
    op.create_index(op.f("ix_consent_logs_guardian_email"), "consent_logs", ["guardian_email"], unique=False)
    op.create_index(op.f("ix_consent_logs_token_jti"), "consent_logs", ["token_jti"], unique=False)
    op.create_index(op.f("ix_consent_logs_status"), "consent_logs", ["status"], unique=False)
    op.create_index(op.f("ix_consent_logs_reason"), "consent_logs", ["reason"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_consent_logs_reason"), table_name="consent_logs")
    op.drop_index(op.f("ix_consent_logs_status"), table_name="consent_logs")
    op.drop_index(op.f("ix_consent_logs_token_jti"), table_name="consent_logs")
    op.drop_index(op.f("ix_consent_logs_guardian_email"), table_name="consent_logs")
    op.drop_index(op.f("ix_consent_logs_student_user_id"), table_name="consent_logs")
    op.drop_index(op.f("ix_consent_logs_student_id"), table_name="consent_logs")
    op.drop_index(op.f("ix_consent_logs_id"), table_name="consent_logs")
    op.drop_table("consent_logs")
