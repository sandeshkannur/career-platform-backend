"""pr44 add contrib_trace to assessment_results

Revision ID: e7cf6ce8be79
Revises: 8c612814971d
Create Date: 2026-02-08 01:14:50.047950

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e7cf6ce8be79'
down_revision: Union[str, None] = '8c612814971d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "assessment_results",
        sa.Column("contrib_trace", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        "ix_assessment_results_contrib_trace",
        "assessment_results",
        ["contrib_trace"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_assessment_results_contrib_trace", table_name="assessment_results")
    op.drop_column("assessment_results", "contrib_trace")