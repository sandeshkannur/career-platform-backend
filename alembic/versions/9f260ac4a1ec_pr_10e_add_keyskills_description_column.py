"""PR-10E add keyskills description column

Revision ID: 9f260ac4a1ec
Revises: 4d2a2c581f31
Create Date: 2026-03-19 00:53:11.670280

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f260ac4a1ec'
down_revision: Union[str, None] = '4d2a2c581f31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "keyskills",
        sa.Column("description", sa.Text(), nullable=True)
    )


def downgrade():
    op.drop_column("keyskills", "description")