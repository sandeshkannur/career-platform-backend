"""PR-10F add explainability_content and student_analytics_summary

Revision ID: f69170dd22cf
Revises: 9f260ac4a1ec
Create Date: 2026-03-20 13:12:17.321359

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "f69170dd22cf"
down_revision: Union[str, None] = "9f260ac4a1ec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_explainability_content_explanation_key", "explainability_content", ["explanation_key"], if_not_exists=True)
    op.create_index("ix_explainability_content_id", "explainability_content", ["id"], if_not_exists=True)
    op.create_index("ix_student_analytics_summary_id", "student_analytics_summary", ["id"], if_not_exists=True)
    op.create_index("ix_student_analytics_summary_scoring_config_version", "student_analytics_summary", ["scoring_config_version"], if_not_exists=True)
    op.create_index("ix_student_analytics_student_version", "student_analytics_summary", ["student_id", "scoring_config_version"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_student_analytics_student_version", table_name="student_analytics_summary")
    op.drop_index("ix_student_analytics_summary_scoring_config_version", table_name="student_analytics_summary")
    op.drop_index("ix_student_analytics_summary_id", table_name="student_analytics_summary")
    op.drop_index("ix_explainability_content_id", table_name="explainability_content")
    op.drop_index("ix_explainability_content_explanation_key", table_name="explainability_content")
