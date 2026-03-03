"""enforce immutable assessment responses

Revision ID: 0ea029cf1a6d
Revises: b839cc4f8ec1
Create Date: 2026-01-17 21:21:20.101073

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0ea029cf1a6d'
down_revision: Union[str, None] = 'b839cc4f8ec1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_assessment_responses_assessment_question",
        "assessment_responses",
        ["assessment_id", "question_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_assessment_responses_assessment_question",
        "assessment_responses",
        type_="unique",
    )