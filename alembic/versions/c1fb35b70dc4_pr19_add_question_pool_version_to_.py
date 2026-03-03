"""PR19 add question_pool_version to assessments

Revision ID: c1fb35b70dc4
Revises: e7cf6ce8be79
Create Date: 2026-02-09 20:39:21.724544

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1fb35b70dc4'
down_revision: Union[str, None] = 'e7cf6ce8be79'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "assessments",
        sa.Column("question_pool_version", sa.String(length=32), nullable=False, server_default="v1"),
    )
    op.create_index("ix_assessments_question_pool_version", "assessments", ["question_pool_version"])

def downgrade():
    op.drop_index("ix_assessments_question_pool_version", table_name="assessments")
    op.drop_column("assessments", "question_pool_version")
