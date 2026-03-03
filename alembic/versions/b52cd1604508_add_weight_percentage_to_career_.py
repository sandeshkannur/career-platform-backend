"""Add weight_percentage to career_keyskill_association

Revision ID: b52cd1604508
Revises: 3e8a4b9f2d31
Create Date: 2025-11-23 08:51:27.673094

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b52cd1604508'
down_revision: Union[str, None] = '3e8a4b9f2d31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "career_keyskill_association",
        sa.Column("weight_percentage", sa.Integer(), nullable=False, server_default="0")
    )


def downgrade():
    op.drop_column("career_keyskill_association", "weight_percentage")