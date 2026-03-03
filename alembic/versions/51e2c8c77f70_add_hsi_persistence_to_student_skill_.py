"""add_hsi_persistence_to_student_skill_scores

Revision ID: 51e2c8c77f70
Revises: 0ea029cf1a6d
Create Date: 2026-01-18 09:56:57.046881

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '51e2c8c77f70'
down_revision: Union[str, None] = '0ea029cf1a6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add additive columns (nullable to avoid breaking existing rows)
    op.add_column("student_skill_scores", sa.Column("hsi_score", sa.Float(), nullable=True))
    op.add_column("student_skill_scores", sa.Column("cps_score_used", sa.Float(), nullable=True))
    op.add_column("student_skill_scores", sa.Column("assessment_version", sa.String(length=20), nullable=True))
    

    # Backfill versions for existing rows using the authoritative assessment record
    op.execute(
        """
        UPDATE student_skill_scores sss
        SET
            assessment_version = a.assessment_version,
            scoring_config_version = a.scoring_config_version
        FROM assessments a
        WHERE sss.assessment_id = a.id
          AND (sss.assessment_version IS NULL OR sss.scoring_config_version IS NULL);
        """
    )


def downgrade() -> None:
    
    op.drop_column("student_skill_scores", "assessment_version")
    op.drop_column("student_skill_scores", "cps_score_used")
    op.drop_column("student_skill_scores", "hsi_score")
