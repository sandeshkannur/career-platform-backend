"""add attribution columns to report_downloads

downloaded_by_user_id / downloaded_by_role record who triggered a report
download (student themselves, or a counsellor/admin pulling it for them).
Both nullable: rows written before this migration carry no attribution and
are deliberately NOT backfilled — the caller identity was not captured at
the time, so any backfill would be a guess.

Revision ID: d8f3b6a1c4e7
Revises: e5a1c7d3b9f2
Create Date: 2026-07-09

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d8f3b6a1c4e7"
down_revision = "e5a1c7d3b9f2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "report_downloads",
        sa.Column("downloaded_by_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "report_downloads",
        sa.Column("downloaded_by_role", sa.String(length=20), nullable=True),
    )
    op.create_foreign_key(
        "fk_report_downloads_downloaded_by_user_id",
        "report_downloads",
        "users",
        ["downloaded_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_report_downloads_downloaded_by_user_id",
        "report_downloads",
        ["downloaded_by_user_id"],
    )


def downgrade():
    op.drop_index("ix_report_downloads_downloaded_by_user_id", table_name="report_downloads")
    op.drop_constraint(
        "fk_report_downloads_downloaded_by_user_id",
        "report_downloads",
        type_="foreignkey",
    )
    op.drop_column("report_downloads", "downloaded_by_role")
    op.drop_column("report_downloads", "downloaded_by_user_id")
