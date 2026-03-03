"""add version pins to assessments

Revision ID: b839cc4f8ec1
Revises: 35d279b3686d
Create Date: 2026-01-17

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b839cc4f8ec1"
down_revision = "35d279b3686d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assessments",
        sa.Column("assessment_version", sa.String(length=32), nullable=False, server_default="v1"),
    )
    op.add_column(
        "assessments",
        sa.Column("scoring_config_version", sa.String(length=32), nullable=False, server_default="v1"),
    )

    op.create_index("ix_assessments_assessment_version", "assessments", ["assessment_version"])
    op.create_index("ix_assessments_scoring_config_version", "assessments", ["scoring_config_version"])

    # Remove defaults after backfill/creation (keeps schema clean)
    op.alter_column("assessments", "assessment_version", server_default=None)
    op.alter_column("assessments", "scoring_config_version", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_assessments_scoring_config_version", table_name="assessments")
    op.drop_index("ix_assessments_assessment_version", table_name="assessments")

    op.drop_column("assessments", "scoring_config_version")
    op.drop_column("assessments", "assessment_version")
