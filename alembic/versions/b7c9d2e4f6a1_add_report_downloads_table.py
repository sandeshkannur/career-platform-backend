"""Add report_downloads table

Append-only log of successful report downloads (scorecard endpoint,
format=pdf|json). Follows the cluster_translations convention: dedicated
table, proper FK constraints.

Revision ID: b7c9d2e4f6a1
Revises: d4f8a1b6c2e7
Create Date: 2026-07-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c9d2e4f6a1'
down_revision: Union[str, None] = 'd4f8a1b6c2e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_downloads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("assessment_id", sa.Integer(), nullable=True),
        sa.Column("format", sa.String(length=10), nullable=False),
        sa.Column("locale", sa.String(length=20), nullable=False),
        sa.Column("tier", sa.String(length=10), nullable=False),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_report_downloads_student_id", "report_downloads", ["student_id"])
    op.create_index("ix_report_downloads_assessment_id", "report_downloads", ["assessment_id"])
    op.create_index("ix_report_downloads_downloaded_at", "report_downloads", ["downloaded_at"])


def downgrade() -> None:
    op.drop_index("ix_report_downloads_downloaded_at", table_name="report_downloads")
    op.drop_index("ix_report_downloads_assessment_id", table_name="report_downloads")
    op.drop_index("ix_report_downloads_student_id", table_name="report_downloads")
    op.drop_table("report_downloads")
