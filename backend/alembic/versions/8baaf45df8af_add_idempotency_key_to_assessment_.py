"""add idempotency key to assessment_responses

Revision ID: 8baaf45df8af
Revises: 51e2c8c77f70
Create Date: 2026-01-18 14:33:58.079979

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8baaf45df8af'
down_revision: Union[str, None] = '51e2c8c77f70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Add nullable column (backward compatible)
    op.add_column(
        "assessment_responses",
        sa.Column("idempotency_key", sa.String(length=80), nullable=True),
    )

    # 2) Unique per assessment for idempotent replays
    op.create_unique_constraint(
        "uq_assessment_responses_assessment_id_idempotency_key",
        "assessment_responses",
        ["assessment_id", "idempotency_key"],
    )

    # 3) Index for fast lookup (assessment_id + idempotency_key)
    op.create_index(
        "ix_assessment_responses_assessment_id_idempotency_key",
        "assessment_responses",
        ["assessment_id", "idempotency_key"],
        unique=False,
    )

def downgrade() -> None:
    op.drop_index(
        "ix_assessment_responses_assessment_id_idempotency_key",
        table_name="assessment_responses",
    )

    op.drop_constraint(
        "uq_assessment_responses_assessment_id_idempotency_key",
        "assessment_responses",
        type_="unique",
    )

    op.drop_column("assessment_responses", "idempotency_key")
