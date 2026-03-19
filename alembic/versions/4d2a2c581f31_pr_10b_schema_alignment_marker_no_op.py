"""PR-10B schema alignment marker (no-op)

Revision ID: 4d2a2c581f31
Revises: 11ec2ee927be
Create Date: 2026-03-18 23:01:28.619298

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4d2a2c581f31'
down_revision: Union[str, None] = '11ec2ee927be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
