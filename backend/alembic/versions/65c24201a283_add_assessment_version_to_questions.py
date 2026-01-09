"""add assessment_version to questions

Revision ID: 65c24201a283
Revises: b52cd1604508
Create Date: 2025-12-22 12:34:54.710329

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '65c24201a283'
down_revision: Union[str, None] = 'b52cd1604508'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add required version column to support version-filtered question sets
    op.add_column(
        "questions",
        sa.Column(
            "assessment_version",
            sa.String(),
            nullable=False,
            server_default="v1",  # existing rows get v1
        ),
    )
    op.create_index(
        op.f("ix_questions_assessment_version"),
        "questions",
        ["assessment_version"],
        unique=False,
    )

    # Optional: remove server_default after backfill, keeps model clean
    op.alter_column("questions", "assessment_version", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_questions_assessment_version"), table_name="questions")
    op.drop_column("questions", "assessment_version")
