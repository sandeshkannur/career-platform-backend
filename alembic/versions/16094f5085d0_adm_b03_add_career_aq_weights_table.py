"""adm_b03_add_career_aq_weights_table

Revision ID: 16094f5085d0
Revises: 60fcdf52c0f5
Create Date: 2026-04-01 15:33:32.481857

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '16094f5085d0'
down_revision: Union[str, None] = '60fcdf52c0f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    ADM-B03: Create career_aq_weights table.

    Stores final calibrated AQ weights per career+round, computed by the
    SME weighted aggregation engine (app/services/sme_aggregation.py).

    Algorithm: Approach B (credentials × calibration composite).
    final_weight = Σ(rating_i × effective_weight_i) / Σ(effective_weight_i)
    where effective_weight_i = credentials_score_i × calibration_score_i

    Rows are never deleted — each round produces new rows.
    is_promoted=False until admin explicitly promotes via ADM-B16.
    """
    op.create_table(
        "career_aq_weights",
        sa.Column("id",           sa.Integer(), nullable=False),
        sa.Column("career_id",    sa.Integer(), nullable=False),
        sa.Column("aq_code",      sa.String(20), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("final_weight",   sa.Float(), nullable=False),
        sa.Column("median_rating",  sa.Float(), nullable=True),
        sa.Column("std_deviation",  sa.Float(), nullable=True),
        sa.Column("sme_count",      sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_promoted",    sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("promoted_at",    sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted_by",    sa.Integer(), nullable=True),
        sa.Column("computed_at",    sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["career_id"],   ["careers.id"]),
        sa.ForeignKeyConstraint(["promoted_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("career_id", "aq_code", "round_number",
                            name="uq_career_aq_weight_career_aq_round"),
    )
    op.create_index("ix_career_aq_weights_id",          "career_aq_weights", ["id"],          unique=False)
    op.create_index("ix_career_aq_weights_career_id",   "career_aq_weights", ["career_id"],   unique=False)
    op.create_index("ix_career_aq_weights_is_promoted", "career_aq_weights", ["is_promoted"], unique=False)


def downgrade() -> None:
    """Remove career_aq_weights table (ADM-B03 rollback)."""
    op.drop_index("ix_career_aq_weights_is_promoted", table_name="career_aq_weights")
    op.drop_index("ix_career_aq_weights_career_id",   table_name="career_aq_weights")
    op.drop_index("ix_career_aq_weights_id",          table_name="career_aq_weights")
    op.drop_table("career_aq_weights")
