"""baseline-clean

Revision ID: 3293623a055c
Revises: b1cd328d0d95
Create Date: 2026-02-23 19:10:51.922234

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3293623a055c'
down_revision: Union[str, None] = 'b1cd328d0d95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Baseline no-op revision.
    # Database already contains the current schema; we only want Alembic
    # to start tracking from this point without applying changes.
    pass


def downgrade() -> None:
    """Downgrade schema."""
    # Baseline no-op revision (no downgrade).
    pass
