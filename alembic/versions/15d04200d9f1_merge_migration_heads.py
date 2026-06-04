"""merge migration heads

Revision ID: 15d04200d9f1
Revises: 06086df126bb, e6f7a8b9c0d1
Create Date: 2026-04-13 13:23:13.873008

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '15d04200d9f1'
down_revision: Union[str, None] = ('06086df126bb', 'e6f7a8b9c0d1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
