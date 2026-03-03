"""pr40 add version bundle to assessment_results

Revision ID: 650d8e341a0f
Revises: 7c0f2237500e
Create Date: 2026-02-06 23:19:58.397706

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '650d8e341a0f'
down_revision: Union[str, None] = '7c0f2237500e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Add nullable columns (backward compatible)
    op.add_column("assessment_results", sa.Column("assessment_version", sa.String(length=32), nullable=True))
    op.add_column("assessment_results", sa.Column("scoring_config_version", sa.String(length=32), nullable=True))
    op.add_column("assessment_results", sa.Column("content_version", sa.String(length=32), nullable=True))

    # 2) Indexes (fast filtering + governance queries)
    op.create_index("ix_assessment_results_assessment_version", "assessment_results", ["assessment_version"], unique=False)
    op.create_index("ix_assessment_results_scoring_config_version", "assessment_results", ["scoring_config_version"], unique=False)
    op.create_index("ix_assessment_results_content_version", "assessment_results", ["content_version"], unique=False)

    # 3) Backfill from authoritative assessments table
    # content_version (beta): default to assessment.assessment_version for now
    op.execute(
        """
        UPDATE assessment_results ar
        SET
            assessment_version = a.assessment_version,
            scoring_config_version = a.scoring_config_version,
            content_version = a.assessment_version
        FROM assessments a
        WHERE ar.assessment_id = a.id
          AND (
            ar.assessment_version IS NULL
            OR ar.scoring_config_version IS NULL
            OR ar.content_version IS NULL
          );
        """
    )


def downgrade() -> None:
    op.drop_index("ix_assessment_results_content_version", table_name="assessment_results")
    op.drop_index("ix_assessment_results_scoring_config_version", table_name="assessment_results")
    op.drop_index("ix_assessment_results_assessment_version", table_name="assessment_results")

    op.drop_column("assessment_results", "content_version")
    op.drop_column("assessment_results", "scoring_config_version")
    op.drop_column("assessment_results", "assessment_version")